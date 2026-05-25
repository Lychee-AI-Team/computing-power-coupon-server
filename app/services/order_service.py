import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cart import CartItem
from app.models.order import Order, OrderItem
from app.models.sku import Sku
from app.services.external_platform import ExternalPlatformService

_EXPIRE_UNIT_DAYS = {"day": 1, "month": 30, "year": 365}


def _calc_expired_at(expire_type: str, expire_value: int) -> datetime:
    days = _EXPIRE_UNIT_DAYS.get(expire_type, 1) * expire_value
    return datetime.now() + timedelta(days=days)


class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_my_orders(
        self, user_id: int, page: int, page_size: int,
        status: int | None = None, order_no: str | None = None, pay_channel: int | None = None,
    ) -> tuple[list[Order], int]:
        conditions = [Order.user_id == user_id]
        if status is not None:
            conditions.append(Order.status == status)
        if order_no:
            conditions.append(Order.order_no.ilike(f"%{order_no}%"))
        if pay_channel is not None:
            conditions.append(Order.pay_channel == pay_channel)

        base_query = select(Order).where(*conditions)
        count_stmt = select(func.count(Order.order_id)).where(*conditions)
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = (
            base_query
            .options(selectinload(Order.items))
            .order_by(Order.order_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def get_order_detail(self, order_id: int, user_id: int) -> Order | None:
        stmt = (
            select(Order)
            .where(Order.order_id == order_id, Order.user_id == user_id)
            .options(selectinload(Order.items))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all_orders(
        self, page: int, page_size: int, user_id: int | None = None,
        status: int | None = None, order_no: str | None = None,
    ) -> tuple[list[Order], int]:
        conditions = []
        if user_id is not None:
            conditions.append(Order.user_id == user_id)
        if status is not None:
            conditions.append(Order.status == status)
        if order_no:
            conditions.append(Order.order_no.ilike(f"%{order_no}%"))

        base_query = select(Order).where(*conditions) if conditions else select(Order)
        count_stmt = select(func.count(Order.order_id)).where(*conditions) if conditions else select(func.count(Order.order_id))
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = (
            base_query
            .options(selectinload(Order.items))
            .order_by(Order.order_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def get_any_order(self, order_id: int) -> Order | None:
        stmt = select(Order).where(Order.order_id == order_id).options(selectinload(Order.items))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_order_by_no(self, order_no: str) -> Order | None:
        stmt = select(Order).where(Order.order_no == order_no).options(selectinload(Order.items))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save_payment_info(self, order: Order, pay_channel: int, pay_info: str) -> None:
        order.pay_channel = pay_channel
        order.pay_info = pay_info
        await self.db.commit()

    async def create_order_from_cart(self, user_id: int, cart_item_ids: list[int]) -> Order:
        stmt = select(CartItem).where(
            CartItem.id.in_(cart_item_ids),
            CartItem.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        cart_items = list(result.scalars().all())

        if not cart_items:
            raise ValueError("未找到有效的购物车项")

        found_ids = {item.id for item in cart_items}
        missing = set(cart_item_ids) - found_ids
        if missing:
            raise ValueError(f"购物车项不存在或不属于当前用户: {missing}")

        sku_ids = list({item.sku_id for item in cart_items})
        sku_stmt = select(Sku).where(Sku.sku_id.in_(sku_ids), Sku.status == 1)
        sku_result = await self.db.execute(sku_stmt)
        skus = {sku.sku_id: sku for sku in sku_result.scalars().all()}

        total_amount = Decimal("0")
        order_items = []
        for cart_item in cart_items:
            sku = skus.get(cart_item.sku_id)
            if not sku:
                raise ValueError(f"SKU {cart_item.sku_id} 不存在或已下架")
            for _ in range(cart_item.quantity):
                order_items.append(
                    OrderItem(
                        sku_id=sku.sku_id,
                        expired_at=_calc_expired_at(sku.expire_type, sku.expire_value),
                    )
                )
            total_amount += sku.face_value * cart_item.quantity

        order = Order(
            order_no=uuid.uuid4().hex[:16].upper(),
            user_id=user_id,
            total_amount=total_amount,
            status=0,
        )
        for oi in order_items:
            order.items.append(oi)

        self.db.add(order)

        for cart_item in cart_items:
            await self.db.delete(cart_item)

        await self.db.commit()
        stmt = select(Order).where(Order.order_id == order.order_id).options(
            selectinload(Order.items).selectinload(OrderItem.sku),
        )
        order = (await self.db.execute(stmt)).scalar_one()
        return order

    async def create_redemption_codes_for_order(
        self, order_id: int, ext_svc: ExternalPlatformService
    ) -> None:
        """逐条抢占 OrderItem 生成兑换码: 行锁 + 立即 commit, 避免并发重复生成与部分失败丢失."""
        item_stmt = select(OrderItem.item_id).where(
            OrderItem.order_id == order_id,
            OrderItem.redemption_status == 0,
        )
        item_ids = [row[0] for row in (await self.db.execute(item_stmt)).all()]

        for item_id in item_ids:
            # 行锁抢占: 同一 item 同时只允许一个协程进入生成流程
            lock_stmt = (
                select(OrderItem)
                .where(OrderItem.item_id == item_id, OrderItem.redemption_status == 0)
                .with_for_update(skip_locked=True)
            )
            item = (await self.db.execute(lock_stmt)).scalar_one_or_none()
            if not item:
                continue

            item.redemption_status = 1  # 标记生成中
            await self.db.commit()

            sku = await self.db.get(Sku, item.sku_id)
            if not sku:
                item.redemption_status = 3
                await self.db.commit()
                continue

            expired_time = int(item.expired_at.timestamp()) if item.expired_at else 0
            quota = int(sku.actual_amount)
            codes = await ext_svc.create_redemption(
                name=sku.sku_name,
                quota=quota,
                count=1,
                expired_time=expired_time,
            )

            if codes and len(codes) > 0:
                item.redemption_code = codes[0]
                item.redemption_status = 2
            else:
                item.redemption_status = 3  # 失败, 留给补偿任务
            await self.db.commit()

    async def mark_order_paid(self, order_no: str, transaction_id: str | None) -> Order | None:
        """行锁更新订单状态: 0 -> 1. 已支付则返回 None, 避免重复触发后续流程."""
        lock_stmt = (
            select(Order)
            .where(Order.order_no == order_no)
            .with_for_update()
            .options(selectinload(Order.items))
        )
        order = (await self.db.execute(lock_stmt)).scalar_one_or_none()
        if not order or order.status != 0:
            return None
        order.status = 1
        if transaction_id:
            order.transaction_id = transaction_id
        await self.db.commit()
        await self.db.refresh(order)
        return order

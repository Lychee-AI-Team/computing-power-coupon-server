import hashlib
import secrets
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.api_key import ApiKey
from app.models.order import Order, OrderItem


_UNSET = object()


class ApiKeyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _generate_raw_key() -> str:
        return "sk_" + secrets.token_hex(16)

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async def create(
        self, user_id: int, name: str, expired_at: datetime | None,
    ) -> tuple[ApiKey, str]:
        raw_key = self._generate_raw_key()
        key_hash = self._hash_key(raw_key)
        key_prefix = raw_key[:11]
        ak = ApiKey(
            user_id=user_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            status=1,
            expired_at=expired_at,
        )
        self.db.add(ak)
        await self.db.commit()
        await self.db.refresh(ak)
        return ak, raw_key

    async def list_keys(
        self, user_id: int, page: int, page_size: int,
    ) -> tuple[list[ApiKey], int]:
        cond = ApiKey.user_id == user_id
        total = (await self.db.execute(select(func.count(ApiKey.id)).where(cond))).scalar() or 0
        stmt = (
            select(ApiKey)
            .where(cond)
            .order_by(ApiKey.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, total

    async def get(self, key_id: int, user_id: int) -> ApiKey | None:
        stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def update(
        self,
        key_id: int,
        user_id: int,
        *,
        name: str | None = None,
        status_: int | None = None,
        expired_at=_UNSET,
    ) -> ApiKey | None:
        ak = await self.get(key_id, user_id)
        if not ak:
            return None
        if name is not None:
            ak.name = name
        if status_ is not None:
            ak.status = status_
        if expired_at is not _UNSET:
            ak.expired_at = expired_at
        await self.db.commit()
        await self.db.refresh(ak)
        return ak

    async def delete(self, key_id: int, user_id: int) -> bool:
        ak = await self.get(key_id, user_id)
        if not ak:
            return False
        await self.db.delete(ak)
        await self.db.commit()
        return True

    async def get_by_raw_key(self, raw_key: str) -> ApiKey | None:
        key_hash = self._hash_key(raw_key)
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def touch_last_used(self, ak: ApiKey) -> None:
        ak.last_used_at = datetime.now()
        await self.db.commit()

    async def list_unexchanged_items(
        self, user_id: int, page: int, page_size: int,
    ) -> tuple[list[OrderItem], int]:
        now = datetime.now()
        conds = [
            Order.user_id == user_id,
            OrderItem.exchange_status == 0,
            OrderItem.redemption_code.is_not(None),
            Order.status.in_([1, 3]),
            (OrderItem.expired_at.is_(None)) | (OrderItem.expired_at > now),
        ]
        count_stmt = (
            select(func.count(OrderItem.item_id))
            .join(Order, OrderItem.order_id == Order.order_id)
            .where(*conds)
        )
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(OrderItem)
            .join(Order, OrderItem.order_id == Order.order_id)
            .where(*conds)
            .order_by(OrderItem.item_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(selectinload(OrderItem.order), selectinload(OrderItem.sku))
        )
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, total

    async def dispatch_unexchanged_items(
        self, user_id: int, order_no: str, dispatch_count: int,
    ) -> list[OrderItem]:
        """按订单号筛选并派发未兑换券: 命中的项写入 dispatched_at, 已派发的不再返回.

        加 FOR UPDATE SKIP LOCKED 行锁防止并发派发同一批 item; 不足时返回实际数量.
        """
        now = datetime.now()
        order_stmt = select(Order).where(Order.order_no == order_no, Order.user_id == user_id)
        order = (await self.db.execute(order_stmt)).scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="订单不存在或不属于当前 API Key 所属用户",
            )
        if order.status not in (1, 3):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="订单状态不支持派发(仅已支付/已完成订单可派发)",
            )

        lock_stmt = (
            select(OrderItem)
            .where(
                OrderItem.order_id == order.order_id,
                OrderItem.exchange_status == 0,
                OrderItem.redemption_code.is_not(None),
                OrderItem.dispatched_at.is_(None),
                (OrderItem.expired_at.is_(None)) | (OrderItem.expired_at > now),
            )
            .order_by(OrderItem.item_id.asc())
            .limit(dispatch_count)
            .with_for_update(skip_locked=True)
        )
        items = list((await self.db.execute(lock_stmt)).scalars().all())
        if not items:
            return []

        for it in items:
            it.dispatched_at = now
        await self.db.commit()

        item_ids = [it.item_id for it in items]
        reload_stmt = (
            select(OrderItem)
            .where(OrderItem.item_id.in_(item_ids))
            .order_by(OrderItem.item_id.asc())
            .options(selectinload(OrderItem.order), selectinload(OrderItem.sku))
        )
        return list((await self.db.execute(reload_stmt)).scalars().all())

    async def query_coupon_status(
        self, user_id: int, order_no: str, redemption_code: str | None = None,
    ) -> list[OrderItem]:
        """按订单号(必填)与兑换码(可选)查询券的兑换状态与派发状态.

        订单不存在或跨用户访问 → 404. 找到订单后返回其 order_items;
        若传入 redemption_code 则进一步过滤. 不限制订单状态(便于查询历史)."""
        order_stmt = select(Order).where(Order.order_no == order_no, Order.user_id == user_id)
        order = (await self.db.execute(order_stmt)).scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="订单不存在或不属于当前 API Key 所属用户",
            )

        conds = [OrderItem.order_id == order.order_id]
        if redemption_code:
            conds.append(OrderItem.redemption_code == redemption_code)
        stmt = (
            select(OrderItem)
            .where(*conds)
            .order_by(OrderItem.item_id.asc())
            .options(selectinload(OrderItem.order), selectinload(OrderItem.sku))
        )
        return list((await self.db.execute(stmt)).scalars().all())

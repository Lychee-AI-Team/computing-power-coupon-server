import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderItem
from app.models.user import User
from app.services.external_platform import ExternalPlatformService

logger = logging.getLogger(__name__)


class ExchangeService:
    def __init__(self, db: AsyncSession, external_service: ExternalPlatformService):
        self.db = db
        self.external_service = external_service

    async def redeem(
        self, redemption_code: str, external_user_id: int, request_ip: str | None = None
    ) -> tuple[OrderItem | None, str | None]:
        """外部平台兑换: 根据 redemption_code 定位 OrderItem, external_user_id 匹配本地用户并写入 exchange_user_id.
        返回 (item, error), error 非空表示失败."""
        # 1. 调第三方接口验证用户是否存在，存在则 upsert 本地 users
        ext_user = await self.external_service.get_user(external_user_id)
        if not ext_user:
            return None, "用户不存在"
        ext_username = ext_user.get("username", f"user_{external_user_id}")
        user = await self.db.get(User, external_user_id)
        if not user:
            user = User(id=external_user_id, username=ext_username)
            self.db.add(user)
            await self.db.commit()
        elif user.username != ext_username:
            user.username = ext_username
            await self.db.commit()
            await self.db.refresh(user)

        # 2. 行锁查询 OrderItem (redemption_code + exchange_status == 0)，同时锁住关联 Order
        lock_stmt = (
            select(OrderItem)
            .where(
                OrderItem.redemption_code == redemption_code,
                OrderItem.exchange_status == 0,
            )
            .with_for_update(skip_locked=True)
            .options(selectinload(OrderItem.order))
        )
        item = (await self.db.execute(lock_stmt)).scalar_one_or_none()

        if item:
            # 对关联 Order 加行锁（等待释放，不 skip），确保读到最新 status
            order_lock_stmt = (
                select(Order)
                .where(Order.order_id == item.order_id)
                .with_for_update()
            )
            order = (await self.db.execute(order_lock_stmt)).scalar_one_or_none()
            if order:
                item.order = order

        if not item:
            # 幂等: 检查是否已兑换，且兑换人匹配
            existing_stmt = select(OrderItem).where(
                OrderItem.redemption_code == redemption_code,
                OrderItem.exchange_status == 1,
                OrderItem.exchange_user_id == user.id,
            )
            existing = (await self.db.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                return existing, None
            # 码存在但被其他人兑换
            taken_stmt = select(OrderItem).where(
                OrderItem.redemption_code == redemption_code,
                OrderItem.exchange_status == 1,
            )
            taken = (await self.db.execute(taken_stmt)).scalar_one_or_none()
            if taken:
                return None, "兑换码已被其他用户兑换"
            return None, "兑换码不存在"

        # 3. 前置校验
        if item.redemption_status != 2:
            return None, "兑换码尚未生成"

        if not item.redemption_code:
            return None, "兑换码不存在"

        order = item.order
        if order.status not in (1, 3):
            return None, "订单尚未支付或已取消"

        if item.expired_at and item.expired_at < datetime.now():
            return None, "该订单项已过期"

        # 4. 更新状态
        old_status = item.exchange_status
        item.exchange_status = 1
        item.exchange_user_id = user.id
        await self.db.commit()
        await self.db.refresh(item)

        logger.info(
            "exchange_redeem: item_id=%d, order_id=%d, external_user_id=%s, user_id=%d, ip=%s, old_status=%d->new_status=1",
            item.item_id, item.order_id, external_user_id, user.id, request_ip, old_status,
        )

        return item, None


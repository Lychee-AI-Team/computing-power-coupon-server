import hashlib
import secrets
from datetime import datetime

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

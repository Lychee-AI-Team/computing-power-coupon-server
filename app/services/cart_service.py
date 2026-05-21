from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cart import CartItem
from app.models.sku import Sku


class CartService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_to_cart(self, user_id: int, sku_id: int, quantity: int = 1) -> CartItem:
        stmt = select(CartItem).where(CartItem.user_id == user_id, CartItem.sku_id == sku_id).options(selectinload(CartItem.sku))
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()

        if item:
            item.quantity += quantity
            await self.db.commit()
            await self.db.refresh(item)
            return item

        item = CartItem(user_id=user_id, sku_id=sku_id, quantity=quantity)
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)

        stmt = select(CartItem).where(CartItem.id == item.id).options(selectinload(CartItem.sku))
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def list_cart(self, user_id: int, page: int, page_size: int) -> tuple[list[CartItem], int]:
        conditions = [CartItem.user_id == user_id]
        count_stmt = select(func.count(CartItem.id)).where(*conditions)
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(CartItem)
            .where(*conditions)
            .options(selectinload(CartItem.sku))
            .order_by(CartItem.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def get_cart_item(self, item_id: int, user_id: int) -> CartItem | None:
        stmt = select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_quantity(self, item_id: int, user_id: int, quantity: int) -> CartItem | None:
        item = await self.get_cart_item(item_id, user_id)
        if not item:
            return None
        item.quantity = quantity
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def remove_item(self, item_id: int, user_id: int) -> bool:
        item = await self.get_cart_item(item_id, user_id)
        if not item:
            return False
        await self.db.delete(item)
        await self.db.commit()
        return True

    async def clear_cart(self, user_id: int) -> int:
        stmt = select(CartItem).where(CartItem.user_id == user_id)
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        count = len(items)
        for item in items:
            await self.db.delete(item)
        await self.db.commit()
        return count

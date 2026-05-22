from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sku import Sku
from app.schemas.sku import SkuCreateRequest, SkuUpdateRequest


class SkuService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_skus(self, page: int, page_size: int) -> tuple[list[Sku], int]:
        count_stmt = select(func.count(Sku.sku_id))
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = select(Sku).order_by(Sku.sku_id.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def list_active_skus(self, page: int, page_size: int) -> tuple[list[Sku], int]:
        conditions = [Sku.status == 1]
        count_stmt = select(func.count(Sku.sku_id)).where(*conditions)
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = (
            select(Sku)
            .where(*conditions)
            .order_by(Sku.sku_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def get_sku_by_id(self, sku_id: int) -> Sku | None:
        stmt = select(Sku).where(Sku.sku_id == sku_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_sku(self, req: SkuCreateRequest) -> Sku:
        sku = Sku(
            sku_name=req.sku_name,
            face_value=req.face_value,
            bonus_amount=req.bonus_amount,
            actual_amount=req.actual_amount,
            status=req.status,
            expire_type=req.expire_type,
            expire_value=req.expire_value,
        )
        self.db.add(sku)
        await self.db.commit()
        await self.db.refresh(sku)
        return sku

    async def update_sku(self, sku: Sku, req: SkuUpdateRequest) -> Sku:
        update_data = req.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(sku, field, value)
        await self.db.commit()
        await self.db.refresh(sku)
        return sku

    async def delete_sku(self, sku: Sku) -> None:
        self.db.delete(sku)
        await self.db.commit()

    async def update_sku_status(self, sku: Sku, status: int) -> Sku:
        sku.status = status
        await self.db.commit()
        await self.db.refresh(sku)
        return sku
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.sku import (
    SkuCreateRequest,
    SkuUpdateRequest,
    SkuStatusRequest,
    SkuItem,
    SkuListResponse,
)
from app.schemas.user import MessageResponse
from app.services.sku_service import SkuService

router = APIRouter(prefix="/api/sku", tags=["SKU管理"])


def _get_sku_service(db: AsyncSession = Depends(get_db)) -> SkuService:
    return SkuService(db)


@router.get("/list", response_model=SkuListResponse, summary="SKU列表", description="分页查询SKU列表，仅管理员可访问")
async def list_skus(
    page: int = Query(default=1, description="页码"),
    page_size: int = Query(default=20, description="每页数量"),
    user: User = Depends(require_admin),
    service: SkuService = Depends(_get_sku_service),
):
    items, total = await service.list_skus(page, page_size)
    return SkuListResponse(
        items=[SkuItem.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{sku_id}", response_model=SkuItem, summary="SKU详情", description="根据ID获取SKU详细信息，仅管理员可访问")
async def get_sku(
    sku_id: int = Path(..., description="SKU ID"),
    user: User = Depends(require_admin),
    service: SkuService = Depends(_get_sku_service),
):
    sku = await service.get_sku_by_id(sku_id)
    if not sku:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")
    return SkuItem.model_validate(sku)


@router.post("/create", response_model=SkuItem, status_code=status.HTTP_201_CREATED, summary="创建SKU", description="创建新的SKU商品，仅管理员可访问")
async def create_sku(
    req: SkuCreateRequest,
    user: User = Depends(require_admin),
    service: SkuService = Depends(_get_sku_service),
):
    sku = await service.create_sku(req)
    return SkuItem.model_validate(sku)


@router.put("/{sku_id}", response_model=SkuItem, summary="更新SKU", description="更新指定SKU的信息，仅管理员可访问")
async def update_sku(
    sku_id: int = Path(..., description="SKU ID"),
    *,
    req: SkuUpdateRequest,
    user: User = Depends(require_admin),
    service: SkuService = Depends(_get_sku_service),
):
    sku = await service.get_sku_by_id(sku_id)
    if not sku:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")
    sku = await service.update_sku(sku, req)
    return SkuItem.model_validate(sku)


@router.delete("/{sku_id}", response_model=MessageResponse, summary="删除SKU", description="删除指定的SKU，仅管理员可访问")
async def delete_sku(
    sku_id: int = Path(..., description="SKU ID"),
    user: User = Depends(require_admin),
    service: SkuService = Depends(_get_sku_service),
):
    sku = await service.get_sku_by_id(sku_id)
    if not sku:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")
    await service.delete_sku(sku)
    return {"message": "SKU删除成功"}


@router.put("/{sku_id}/status", response_model=SkuItem, summary="更新SKU状态", description="启用或禁用指定SKU，仅管理员可访问")
async def update_sku_status(
    sku_id: int = Path(..., description="SKU ID"),
    *,
    req: SkuStatusRequest,
    user: User = Depends(require_admin),
    service: SkuService = Depends(_get_sku_service),
):
    sku = await service.get_sku_by_id(sku_id)
    if not sku:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found")
    sku = await service.update_sku_status(sku, req.status)
    return SkuItem.model_validate(sku)
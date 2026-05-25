from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.cart import CartAddRequest, CartItemInfo, CartListResponse, CartUpdateRequest
from app.schemas.user import MessageResponse
from app.services.cart_service import CartService

router = APIRouter(prefix="/api/cart", tags=["购物车"])


def _get_cart_service(db: AsyncSession = Depends(get_db)) -> CartService:
    return CartService(db)


def _to_cart_item_info(item) -> CartItemInfo:
    return CartItemInfo(
        id=item.id,
        sku_id=item.sku_id,
        sku_name=item.sku.sku_name,
        face_value=item.sku.face_value,
        bonus_amount=item.sku.bonus_amount,
        actual_amount=item.sku.actual_amount,
        sku_status=item.sku.status,
        quantity=item.quantity,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/add", response_model=CartItemInfo, status_code=status.HTTP_201_CREATED, summary="添加到购物车", description="将SKU添加到购物车，已存在则累加数量")
async def add_to_cart(
    req: CartAddRequest,
    user: User = Depends(get_current_user),
    service: CartService = Depends(_get_cart_service),
):
    item = await service.add_to_cart(user.id, req.sku_id, req.quantity)
    await service.db.refresh(item)  # 确保 sku relationship 加载
    return _to_cart_item_info(item)


@router.get("/list", response_model=CartListResponse, summary="购物车列表", description="分页查询当前用户的购物车列表")
async def list_cart(
    page: int = Query(default=1, description="页码"),
    page_size: int = Query(default=20, description="每页数量"),
    user: User = Depends(get_current_user),
    service: CartService = Depends(_get_cart_service),
):
    items, total = await service.list_cart(user.id, page, page_size)
    return CartListResponse(
        items=[_to_cart_item_info(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.put("/{item_id}", response_model=CartItemInfo, summary="修改数量", description="修改购物车中指定项的数量")
async def update_cart_item(
    item_id: int = Path(..., description="购物车项ID"),
    *,
    req: CartUpdateRequest,
    user: User = Depends(get_current_user),
    service: CartService = Depends(_get_cart_service),
):
    item = await service.update_quantity(item_id, user.id, req.quantity)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="购物车项不存在")
    return _to_cart_item_info(item)


@router.delete("/clear/all", response_model=MessageResponse, summary="清空购物车", description="清空当前用户购物车中的所有项")
async def clear_cart(
    user: User = Depends(get_current_user),
    service: CartService = Depends(_get_cart_service),
):
    count = await service.clear_cart(user.id)
    return {"message": f"已清空购物车，共移除{count}项"}


@router.delete("/{item_id}", response_model=MessageResponse, summary="删除购物车项", description="删除购物车中指定的SKU项")
async def remove_cart_item(
    item_id: int = Path(..., description="购物车项ID"),
    user: User = Depends(get_current_user),
    service: CartService = Depends(_get_cart_service),
):
    ok = await service.remove_item(item_id, user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="购物车项不存在")
    return {"message": "已从购物车移除"}

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_admin
from app.core.database import get_db
from app.core.external_client import get_wechat_client
from app.models.user import User
from app.schemas.order import (
    CreateOrderRequest,
    OrderInfo,
    OrderListResponse,
)
from app.services.order_service import OrderService
from app.services.wechat_pay_service import WechatPayService

router = APIRouter(prefix="/api/order", tags=["订单管理"])


def _get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
    return OrderService(db)


async def _get_pay_service() -> WechatPayService:
    return WechatPayService(await get_wechat_client())


# --- 用户端接口 ---

@router.get("/my", response_model=OrderListResponse, summary="我的订单列表", description="分页查询当前用户的订单列表，支持按状态、订单号和支付方式筛选")
async def list_my_orders(
    page: int = Query(default=1, description="页码"),
    page_size: int = Query(default=20, description="每页数量"),
    status: int | None = Query(default=None, description="订单状态，0-待支付 1-已支付 2-已取消 3-已完成"),
    order_no: str | None = Query(default=None, description="订单编号"),
    pay_channel: int | None = Query(default=None, description="支付方式，1-微信 2-支付宝"),
    user: User = Depends(get_current_user),
    service: OrderService = Depends(_get_order_service),
    pay_svc: WechatPayService = Depends(_get_pay_service),
):
    items, total = await service.list_my_orders(user.id, page, page_size, status, order_no, pay_channel)
    items = await service.check_and_cancel_list_if_timeout(items, pay_svc)
    return OrderListResponse(
        items=[OrderInfo.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/my/{order_id}", response_model=OrderInfo, summary="我的订单详情", description="获取当前用户指定订单的详细信息")
async def get_my_order(
    order_id: int = Path(..., description="订单ID"),
    user: User = Depends(get_current_user),
    service: OrderService = Depends(_get_order_service),
    pay_svc: WechatPayService = Depends(_get_pay_service),
):
    order = await service.get_order_detail(order_id, user.id)
    order = await service.check_and_cancel_if_timeout(order, pay_svc)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderInfo.model_validate(order)


@router.post("/create", response_model=OrderInfo, status_code=status.HTTP_201_CREATED, summary="创建订单", description="从购物车选择商品创建订单，下单成功后自动删除对应购物车项")
async def create_order(
    req: CreateOrderRequest,
    user: User = Depends(get_current_user),
    service: OrderService = Depends(_get_order_service),
):
    try:
        order = await service.create_order_from_cart(user.id, req.cart_item_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return OrderInfo.model_validate(order)


# --- 管理员端接口 ---

@router.get("/admin/list", response_model=OrderListResponse, summary="管理员-订单列表", description="管理员分页查询所有订单，支持按用户、状态和订单号筛选")
async def admin_list_orders(
    page: int = Query(default=1, description="页码"),
    page_size: int = Query(default=20, description="每页数量"),
    user_id: int | None = Query(default=None, description="用户ID"),
    status: int | None = Query(default=None, description="订单状态，0-待支付 1-已支付 2-已取消 3-已完成"),
    order_no: str | None = Query(default=None, description="订单编号"),
    admin: dict = Depends(require_admin),
    service: OrderService = Depends(_get_order_service),
    pay_svc: WechatPayService = Depends(_get_pay_service),
):
    items, total = await service.list_all_orders(page, page_size, user_id, status, order_no)
    items = await service.check_and_cancel_list_if_timeout(items, pay_svc)
    return OrderListResponse(
        items=[OrderInfo.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/admin/{order_id}", response_model=OrderInfo, summary="管理员-订单详情", description="管理员获取任意订单的详细信息")
async def admin_get_order(
    order_id: int = Path(..., description="订单ID"),
    admin: dict = Depends(require_admin),
    service: OrderService = Depends(_get_order_service),
    pay_svc: WechatPayService = Depends(_get_pay_service),
):
    order = await service.get_any_order(order_id)
    order = await service.check_and_cancel_if_timeout(order, pay_svc)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderInfo.model_validate(order)

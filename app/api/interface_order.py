import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.api_key_auth import get_user_by_api_key
from app.core.config import settings
from app.core.database import async_session, get_db
from app.core.external_client import get_external_client
from app.core.rate_limit import check_rate_limit
from app.models.api_key import ApiKey
from app.models.order import Order, OrderItem
from app.models.user import User
from app.schemas.interface_order import (
    ORDER_STATUS_FAILED,
    ORDER_STATUS_GENERATING,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TEXT,
    InterfaceOrderCreateResponse,
    InterfaceOrderRequest,
    InterfaceOrderStatusResponse,
)
from app.services.external_platform import ExternalPlatformService
from app.services.order_service import OrderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interface/order", tags=["外部接口-接口下单"])


async def _generate_codes_task(order_id: int, client: httpx.AsyncClient) -> None:
    """后台任务: 使用独立 DB session 为接口订单异步生成兑换码."""
    try:
        async with async_session() as session:
            await OrderService(session).create_redemption_codes_for_order(
                order_id, ExternalPlatformService(client),
            )
    except Exception as e:
        logger.exception("interface_generate_codes_task failed: order_id=%s err=%s", order_id, e)


def _require_whitelisted(user: User) -> None:
    if user.id not in settings.interface_order_allowed_user_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该用户无接口下单权限")


@router.post(
    "/create",
    response_model=InterfaceOrderCreateResponse,
    summary="接口下单直发算力券",
    description="固定白名单用户通过 X-API-Key 直接下单，绕过支付(pay_channel=3)，立即返回平台订单号，兑换码后台异步生成，请用查询接口获取卡密",
)
async def create_order_via_interface(
    req: InterfaceOrderRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_external_client),
):
    user, ak = auth
    if req.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key 与 user_id 不匹配")
    _require_whitelisted(user)

    await check_rate_limit(f"rate_limit:interface_order:key:{ak.id}", max_requests=60, window_seconds=60)
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"rate_limit:interface_order:ip:{ip}", max_requests=200, window_seconds=60)

    svc = OrderService(db)
    try:
        order = await svc.create_order_via_interface(
            req.user_id, req.sku_id, req.quantity, req.client_order_no,
        )
    except ValueError as e:
        return InterfaceOrderCreateResponse(success=False, message=str(e))

    # 兑换码异步生成, 不阻塞响应; 调用方用 /status 查询卡密与生成状态
    background_tasks.add_task(_generate_codes_task, order.order_id, client)

    return InterfaceOrderCreateResponse(
        success=True,
        message="下单成功，兑换码生成中，请用查询接口获取卡密",
        order_no=order.order_no,
        client_order_no=order.client_order_no,
    )


@router.get(
    "/status",
    response_model=InterfaceOrderStatusResponse,
    summary="查询接口订单卡密与生成状态",
    description="按客户侧订单号查询订单生成状态(generating/failed/success)，仅 success 时返回卡密数组；需 user_id 与 X-API-Key 一致且在白名单内；业务上需保证 (user_id, client_order_no) 唯一",
)
async def query_interface_order_status(
    request: Request,
    user_id: int = Query(..., gt=0, description="用户ID, 必须与 X-API-Key 所属用户一致"),
    client_order_no: str = Query(..., min_length=1, max_length=64, description="客户侧订单号(创建接口传入的 client_order_no)"),
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    user, ak = auth
    if user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key 与 user_id 不匹配")
    _require_whitelisted(user)

    await check_rate_limit(f"rate_limit:interface_order_status:key:{ak.id}", max_requests=120, window_seconds=60)
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"rate_limit:interface_order_status:ip:{ip}", max_requests=300, window_seconds=60)

    # 按 (user_id, client_order_no) 查订单; 业务上需保证唯一
    stmt = (
        select(Order)
        .where(Order.client_order_no == client_order_no, Order.user_id == user.id)
        .options(selectinload(Order.items).selectinload(OrderItem.sku))
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="订单不存在或不属于当前 API Key 所属用户",
        )

    items = order.items
    statuses = [it.redemption_status for it in items]
    if any(s == 3 for s in statuses):
        order_status = ORDER_STATUS_FAILED
        codes: list[str] = []
    elif items and all(s == 2 for s in statuses):
        order_status = ORDER_STATUS_SUCCESS
        codes = [it.redemption_code for it in items if it.redemption_code]
    else:
        order_status = ORDER_STATUS_GENERATING
        codes = []

    return InterfaceOrderStatusResponse(
        success=True,
        message="查询成功",
        order_no=order.order_no,
        order_status=order_status,
        order_status_text=ORDER_STATUS_TEXT[order_status],
        total=len(items),
        codes=codes,
    )

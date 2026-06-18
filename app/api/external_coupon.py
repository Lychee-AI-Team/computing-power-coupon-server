from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_auth import get_user_by_api_key
from app.core.database import get_db
from app.core.rate_limit import check_rate_limit
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import (
    ExternalCouponItem,
    ExternalCouponListResponse,
    ExternalCouponStatusItem,
    ExternalCouponStatusResponse,
)
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/api/external/coupons", tags=["外部接口-未兑换券"])

EXCHANGE_STATUS_TEXT = {0: "未兑换", 1: "已兑换", 2: "已退款", 3: "已过期"}


def _external_coupon_status(exchange_status: int, expired_at) -> int:
    if exchange_status == 0 and expired_at is not None:
        from datetime import datetime

        if expired_at <= datetime.now():
            return 3
    return exchange_status


def _get_service(db: AsyncSession = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(db)


@router.get(
    "/unexchanged",
    response_model=ExternalCouponListResponse,
    summary="派发未兑换算力券",
    description=(
        "第三方通过 X-API-Key 请求头, 按订单号与派发数量从该 Key 所属用户名下未兑换券中派发. "
        "返回的券会被打上派发标记并持久化, 同一张券不会被二次派发."
    ),
)
async def list_unexchanged_coupons(
    request: Request,
    order_no: str = Query(..., min_length=1, max_length=64, description="订单号(必填)"),
    dispatch_count: int = Query(..., gt=0, description="本次派发数量, 必须大于 0"),
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    svc: ApiKeyService = Depends(_get_service),
):
    user, ak = auth

    await check_rate_limit(f"rate_limit:external_coupon:key:{ak.id}", max_requests=60, window_seconds=60)
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"rate_limit:external_coupon:ip:{ip}", max_requests=200, window_seconds=60)

    items = await svc.dispatch_unexchanged_items(user.id, order_no, dispatch_count)
    remaining_undispatched_count = await svc.count_remaining_undispatched_items(user.id, order_no)
    out = [
        ExternalCouponItem(
            item_id=it.item_id,
            order_no=it.order.order_no,
            sku_id=it.sku_id,
            sku_name=it.sku.sku_name,
            face_value=it.sku.face_value,
            actual_amount=it.sku.actual_amount,
            redemption_code=it.redemption_code,
            expired_at=it.expired_at,
            dispatched_at=it.dispatched_at,
            created_at=it.created_at,
        )
        for it in items
    ]
    return ExternalCouponListResponse(
        items=out,
        total=len(out),
        remaining_undispatched_count=remaining_undispatched_count,
        page=1,
        page_size=dispatch_count,
    )


@router.get(
    "/status",
    response_model=ExternalCouponStatusResponse,
    summary="查询算力券状态",
    description=(
        "第三方通过 X-API-Key 查询某订单下算力券的兑换状态与派发状态. "
        "order_no 必填; 可选传 redemption_code 进一步过滤到具体一张券."
    ),
)
async def query_coupon_status(
    request: Request,
    order_no: str = Query(..., min_length=1, max_length=64, description="订单号(必填)"),
    redemption_code: str | None = Query(
        default=None, max_length=128, description="兑换码(可选), 传入后只返回该兑换码对应的券",
    ),
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    svc: ApiKeyService = Depends(_get_service),
):
    user, ak = auth

    await check_rate_limit(f"rate_limit:external_coupon:key:{ak.id}", max_requests=60, window_seconds=60)
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"rate_limit:external_coupon:ip:{ip}", max_requests=200, window_seconds=60)

    items = await svc.query_coupon_status(user.id, order_no, redemption_code)
    out = []
    for it in items:
        status_ = _external_coupon_status(it.exchange_status, it.expired_at)
        out.append(
            ExternalCouponStatusItem(
                item_id=it.item_id,
                order_no=it.order.order_no,
                sku_id=it.sku_id,
                sku_name=it.sku.sku_name,
                redemption_code=it.redemption_code,
                exchange_status=status_,
                exchange_status_text=EXCHANGE_STATUS_TEXT.get(status_, "未知"),
                exchanged_at=it.exchanged_at,
                dispatched=it.dispatched_at is not None,
                dispatched_at=it.dispatched_at,
                expired_at=it.expired_at,
                created_at=it.created_at,
            )
        )
    return ExternalCouponStatusResponse(items=out, total=len(out))

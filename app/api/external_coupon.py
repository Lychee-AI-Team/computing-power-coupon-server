from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_auth import get_user_by_api_key
from app.core.database import get_db
from app.core.rate_limit import check_rate_limit
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import ExternalCouponItem, ExternalCouponListResponse
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/api/external/coupons", tags=["外部接口-未兑换券"])


def _get_service(db: AsyncSession = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(db)


@router.get(
    "/unexchanged",
    response_model=ExternalCouponListResponse,
    summary="查询未兑换算力券",
    description="第三方通过 X-API-Key 请求头查询当前 Key 所属用户名下的未兑换算力券列表(含兑换码)",
)
async def list_unexchanged_coupons(
    request: Request,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    svc: ApiKeyService = Depends(_get_service),
):
    user, ak = auth

    await check_rate_limit(f"rate_limit:external_coupon:key:{ak.id}", max_requests=60, window_seconds=60)
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"rate_limit:external_coupon:ip:{ip}", max_requests=200, window_seconds=60)

    items, total = await svc.list_unexchanged_items(user.id, page, page_size)
    out = [
        ExternalCouponItem(
            item_id=it.item_id,
            order_id=it.order_id,
            order_no=it.order.order_no,
            sku_id=it.sku_id,
            sku_name=it.sku.sku_name,
            face_value=it.sku.face_value,
            actual_amount=it.sku.actual_amount,
            redemption_code=it.redemption_code,
            expired_at=it.expired_at,
            created_at=it.created_at,
        )
        for it in items
    ]
    return ExternalCouponListResponse(items=out, total=total, page=page, page_size=page_size)

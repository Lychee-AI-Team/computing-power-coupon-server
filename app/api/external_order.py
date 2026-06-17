from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_auth import get_user_by_api_key
from app.core.database import get_db
from app.core.rate_limit import check_rate_limit
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import ExternalOrderInfo, ExternalOrderListResponse
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/api/external/orders", tags=["外部接口-订单查询"])


def _get_service(db: AsyncSession = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(db)


@router.get(
    "",
    response_model=ExternalOrderListResponse,
    summary="查询订单列表",
    description="第三方通过 X-API-Key 查询当前 Key 所属用户的全部订单摘要信息",
)
async def list_external_orders(
    request: Request,
    auth: tuple[User, ApiKey] = Depends(get_user_by_api_key),
    svc: ApiKeyService = Depends(_get_service),
):
    user, ak = auth

    await check_rate_limit(f"rate_limit:external_order:key:{ak.id}", max_requests=60, window_seconds=60)
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"rate_limit:external_order:ip:{ip}", max_requests=200, window_seconds=60)

    rows = await svc.list_external_orders(user.id)
    items = [
        ExternalOrderInfo(
            order_no=order.order_no,
            created_at=order.created_at,
            total_amount=order.total_amount,
            status=order.status,
            refunded_amount=order.refunded_amount,
            expired_at=expired_at,
        )
        for order, expired_at in rows
    ]
    return ExternalOrderListResponse(items=items, total=len(items))

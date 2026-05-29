import hashlib

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exchange_auth import require_exchange_token
from app.core.external_client import get_external_client
from app.core.rate_limit import check_rate_limit
from app.schemas.exchange import (
    ExternalRedeemRequest, ExternalRedeemResponse, ExternalRedeemData,
)
from app.services.exchange_service import ExchangeService
from app.services.external_platform import ExternalPlatformService

router = APIRouter(prefix="/api/exchange", tags=["外部接口"])


def _get_exchange_service(
    db: AsyncSession = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_external_client),
) -> ExchangeService:
    external_service = ExternalPlatformService(client)
    return ExchangeService(db, external_service)


@router.post(
    "/redeem",
    response_model=ExternalRedeemResponse,
    summary="外部平台兑换",
    description="外部平台调用此接口将兑换码标记为已兑换，需在请求头携带 X-Exchange-Token",
)
async def external_redeem(
    req: ExternalRedeemRequest,
    request: Request,
    _: None = Depends(require_exchange_token),
    service: ExchangeService = Depends(_get_exchange_service),
):
    # 限流: 按 IP 200次/分钟
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"rate_limit:exchange:ip:{ip}", max_requests=200, window_seconds=60)

    # 限流: 按 redemption_code 10次/分钟
    code_hash = hashlib.sha256(req.redemption_code.encode()).hexdigest()[:16]
    await check_rate_limit(f"rate_limit:exchange:code:{code_hash}", max_requests=10, window_seconds=60)

    item, error = await service.redeem(
        redemption_code=req.redemption_code,
        external_user_id=req.external_user_id,
        request_ip=ip,
    )

    if error:
        return ExternalRedeemResponse(success=False, message=error)

    return ExternalRedeemResponse(
        success=True,
        message="兑换成功",
        data=ExternalRedeemData.model_validate(item),
    )

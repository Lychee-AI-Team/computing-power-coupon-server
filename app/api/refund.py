import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_token_payload, require_admin
from app.core.database import async_session, get_db
from app.core.external_client import get_external_client, get_wechat_client
from app.schemas.refund import (
    CreateRefundRequest,
    RefundCreateResponse,
    RefundInfo,
    RefundListResponse,
)
from app.services.external_platform import ExternalPlatformService
from app.services.refund_service import REFUND_STATUS_TEXT, RefundService
from app.services.wechat_pay_service import WechatPayService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/refund", tags=["退款管理"])


def _get_refund_service(db: AsyncSession = Depends(get_db)) -> RefundService:
    return RefundService(db)


def _get_pay_service(client: httpx.AsyncClient = Depends(get_wechat_client)) -> WechatPayService:
    return WechatPayService(client)


def _get_ext_service(client: httpx.AsyncClient = Depends(get_external_client)) -> ExternalPlatformService:
    return ExternalPlatformService(client)


@router.post(
    "/create",
    response_model=RefundCreateResponse,
    summary="管理员发起退款",
    description="管理员对指定订单发起微信退款，支持部分退款。可选传入 item_ids 关联具体订单项，退款成功后自动作废兑换码并将对应订单项标记为已退款",
)
async def create_refund(
    req: CreateRefundRequest,
    payload: dict = Depends(require_admin),
    refund_svc: RefundService = Depends(_get_refund_service),
    pay_svc: WechatPayService = Depends(_get_pay_service),
    ext_svc: ExternalPlatformService = Depends(_get_ext_service),
):
    operator_id = int(payload.get("sub", 0))
    if operator_id <= 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid operator")

    refund = await refund_svc.create_refund(
        order_id=req.order_id,
        refund_amount=req.refund_amount,
        reason=req.reason,
        operator_id=operator_id,
        pay_svc=pay_svc,
        refund_type=req.refund_type,
        item_ids=req.item_ids,
        ext_svc=ext_svc,
    )
    return RefundCreateResponse(
        refund_id=refund.refund_id,
        refund_no=refund.refund_no,
        refund_amount=refund.refund_amount,
        status=refund.status,
        status_text=REFUND_STATUS_TEXT.get(refund.status, "未知"),
    )


@router.post(
    "/notify",
    summary="微信退款回调",
    description="接收微信退款结果通知，验签后更新退款状态",
)
async def refund_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
    ext_client: httpx.AsyncClient = Depends(get_external_client),
):
    body = await request.body()
    signature = request.headers.get("Wechatpay-Signature", "")
    timestamp = request.headers.get("Wechatpay-Timestamp", "")
    nonce = request.headers.get("Wechatpay-Nonce", "")
    serial = request.headers.get("Wechatpay-Serial", "")

    data = WechatPayService.verify_notify_sign(body, signature, timestamp, nonce, serial)
    if not data:
        logger.error("refund_notify: signature verification failed")
        return WechatPayService.build_notify_reply()

    out_refund_no = data.get("out_refund_no")
    refund_status = (data.get("refund_status") or "").upper()
    wechat_refund_id = data.get("refund_id")
    if not out_refund_no:
        logger.warning("refund_notify: missing out_refund_no, payload=%s", data)
        return WechatPayService.build_notify_reply()

    import json
    try:
        payload_str = json.dumps(data, ensure_ascii=False)
    except Exception:
        payload_str = str(data)

    refund_svc = RefundService(db)
    if refund_status == "SUCCESS":
        ext_svc = ExternalPlatformService(ext_client) if ext_client else None
        await refund_svc.apply_refund_success(
            out_refund_no, wechat_refund_id, payload_str, ext_svc=ext_svc,
        )
    else:
        await refund_svc.apply_refund_failure(
            out_refund_no, f"WeChat refund_status={refund_status}", payload_str,
        )
    return WechatPayService.build_notify_reply()


@router.get(
    "/admin/list",
    response_model=RefundListResponse,
    summary="管理员退款列表",
    description="管理员分页查询退款记录",
)
async def admin_list_refunds(
    order_no: str | None = Query(default=None, description="订单号过滤"),
    refund_no: str | None = Query(default=None, description="退款单号过滤"),
    status_: int | None = Query(default=None, alias="status", description="退款状态过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    _: dict = Depends(require_admin),
    refund_svc: RefundService = Depends(_get_refund_service),
):
    items, total = await refund_svc.list_refunds(
        order_no=order_no, refund_no=refund_no,
        status_=status_, page=page, page_size=page_size,
    )
    return RefundListResponse(
        items=[RefundInfo.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/admin/{refund_id}",
    response_model=RefundInfo,
    summary="管理员退款详情",
    description="管理员查询单条退款详情",
)
async def admin_get_refund(
    refund_id: int = Path(..., gt=0, description="退款记录ID"),
    _: dict = Depends(require_admin),
    refund_svc: RefundService = Depends(_get_refund_service),
):
    refund = await refund_svc.get_refund_detail(refund_id)
    if not refund:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund not found")
    return RefundInfo.model_validate(refund)


@router.post(
    "/admin/{refund_id}/sync",
    response_model=RefundInfo,
    summary="主动同步退款状态",
    description="管理员主动从微信查询并同步退款状态，作为回调丢失时的兜底",
)
async def admin_sync_refund(
    refund_id: int = Path(..., gt=0, description="退款记录ID"),
    _: dict = Depends(require_admin),
    refund_svc: RefundService = Depends(_get_refund_service),
    pay_svc: WechatPayService = Depends(_get_pay_service),
    ext_svc: ExternalPlatformService = Depends(_get_ext_service),
):
    refund = await refund_svc.sync_refund_from_wechat(refund_id, pay_svc, ext_svc=ext_svc)
    if not refund:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund not found")
    return RefundInfo.model_validate(refund)
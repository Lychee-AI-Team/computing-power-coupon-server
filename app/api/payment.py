import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.external_client import get_external_client
from app.models.order import Order
from app.models.user import User
from app.schemas.payment import CreatePaymentRequest, PaymentNotifyResponse, PaymentResponse, PaymentStatusResponse
from app.services.order_service import OrderService
from app.services.wechat_pay_service import WechatPayService

router = APIRouter(prefix="/api/payment", tags=["支付管理"])


def _get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
    return OrderService(db)


def _get_pay_service(client: httpx.AsyncClient = Depends(get_external_client)) -> WechatPayService:
    return WechatPayService(client)


_STATUS_MAP = {0: "待支付", 1: "已支付", 2: "已取消", 3: "已完成"}


@router.post("/native", response_model=PaymentResponse, summary="微信Native支付", description="创建微信Native支付订单，返回扫码支付链接")
async def create_native_payment(
    req: CreatePaymentRequest,
    user: User = Depends(get_current_user),
    order_svc: OrderService = Depends(_get_order_service),
    pay_svc: WechatPayService = Depends(_get_pay_service),
):
    order = await order_svc.get_order_detail(req.order_id, user.id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status != 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order status is not pending")

    # 微信金额单位是分
    total_fee = int(order.total_amount * 100)

    result = await pay_svc.create_native_payment(
        order_no=order.order_no,
        total_fee=total_fee,
        body="算力券充值",
    )
    await order_svc.save_payment_info(order, pay_channel=1, pay_info=json.dumps(result))
    return PaymentResponse(**result)


@router.post("/notify", response_model=PaymentNotifyResponse, summary="微信支付回调", description="接收微信支付结果通知，验签后更新订单状态")
async def payment_notify(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    signature = request.headers.get("Wechatpay-Signature", "")
    timestamp = request.headers.get("Wechatpay-Timestamp", "")
    nonce = request.headers.get("Wechatpay-Nonce", "")
    serial = request.headers.get("Wechatpay-Serial", "")

    data = WechatPayService.verify_notify_sign(body, signature, timestamp, nonce, serial)
    if not data:
        return WechatPayService.build_notify_reply()

    order_no = data.get("out_trade_no")
    trade_state = data.get("trade_state", "")
    if not order_no or trade_state != "SUCCESS":
        return WechatPayService.build_notify_reply()

    order_svc = OrderService(db)
    order = await order_svc.get_order_by_no(order_no)
    if not order:
        return WechatPayService.build_notify_reply()

    if order.status == 0:
        order.status = 1
        if data.get("transaction_id"):
            order.transaction_id = data["transaction_id"]
        await db.commit()

    return WechatPayService.build_notify_reply()


@router.get("/status/{order_id}", response_model=PaymentStatusResponse, summary="支付状态查询", description="查询指定订单的支付状态")
async def get_payment_status(
    order_id: int = Path(..., description="订单ID"),
    user: User = Depends(get_current_user),
    order_svc: OrderService = Depends(_get_order_service),
):
    order = await order_svc.get_order_detail(order_id, user.id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    paid_at = order.updated_at if order.status == 1 else None
    return PaymentStatusResponse(
        order_id=order.order_id,
        order_no=order.order_no,
        status=order.status,
        status_text=_STATUS_MAP.get(order.status, "未知"),
        paid_at=paid_at,
    )
import logging
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.order import Order
from app.models.refund import Refund
from app.services.wechat_pay_service import WechatPayService

logger = logging.getLogger(__name__)

REFUND_STATUS_TEXT = {0: "处理中", 1: "成功", 2: "失败", 3: "异常"}


def _generate_refund_no() -> str:
    return "R" + uuid.uuid4().hex[:20].upper()


class RefundService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_refund(
        self,
        order_id: int,
        refund_amount: Decimal,
        reason: str | None,
        operator_id: int,
        pay_svc: WechatPayService,
    ) -> Refund:
        """管理员发起退款. 先落库本地流水, 再调用微信 API, 根据响应同步状态."""
        if not settings.WECHAT_REFUND_NOTIFY_URL:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="WeChat refund notify url is not configured",
            )

        lock_stmt = (
            select(Order)
            .where(Order.order_id == order_id)
            .with_for_update()
        )
        order = (await self.db.execute(lock_stmt)).scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        if order.status not in (1, 3, 4):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only paid/completed/partially-refunded order can be refunded",
            )
        if order.pay_channel != 1 or not order.transaction_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only WeChat-paid order with transaction_id can be refunded",
            )
        already = order.refunded_amount or Decimal("0")
        if refund_amount + already > order.total_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Refund amount exceeds remaining: max={order.total_amount - already}",
            )

        refund = Refund(
            refund_no=_generate_refund_no(),
            order_id=order.order_id,
            order_no=order.order_no,
            refund_amount=refund_amount,
            total_amount=order.total_amount,
            reason=reason,
            status=0,
            transaction_id=order.transaction_id,
            operator_id=operator_id,
            channel=1,
        )
        self.db.add(refund)
        await self.db.commit()
        await self.db.refresh(refund)

        try:
            result = await pay_svc.create_refund(
                out_trade_no=order.order_no,
                out_refund_no=refund.refund_no,
                refund_fee=int(refund_amount * 100),
                total_fee=int(order.total_amount * 100),
                reason=reason,
                notify_url=settings.WECHAT_REFUND_NOTIFY_URL,
            )
        except HTTPException as e:
            await self._mark_refund_failed(refund.refund_no, str(e.detail))
            raise
        except Exception as e:
            logger.exception("create_refund call failed: refund_no=%s", refund.refund_no)
            await self._mark_refund_failed(refund.refund_no, f"WeChat API error: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="WeChat refund request failed",
            )

        wechat_refund_id = result.get("refund_id")
        wechat_status = (result.get("status") or "").upper()
        if wechat_status == "SUCCESS":
            return await self.apply_refund_success(
                refund.refund_no, wechat_refund_id, _safe_dump(result),
            ) or refund
        elif wechat_status == "PROCESSING":
            await self._update_refund_wechat_id(refund.refund_no, wechat_refund_id)
            await self.db.refresh(refund)
            return refund
        else:
            await self._mark_refund_abnormal(
                refund.refund_no, wechat_refund_id,
                f"WeChat returned status={wechat_status}", _safe_dump(result),
            )
            await self.db.refresh(refund)
            return refund

    async def apply_refund_success(
        self, refund_no: str, wechat_refund_id: str | None, notify_payload: str | None,
    ) -> Refund | None:
        """回调成功分支: 幂等更新退款记录和订单累计退款金额."""
        lock_stmt = select(Refund).where(Refund.refund_no == refund_no).with_for_update()
        refund = (await self.db.execute(lock_stmt)).scalar_one_or_none()
        if not refund:
            logger.warning("apply_refund_success: refund_no not found: %s", refund_no)
            return None
        if refund.status == 1:
            return refund

        order_lock_stmt = (
            select(Order).where(Order.order_id == refund.order_id).with_for_update()
        )
        order = (await self.db.execute(order_lock_stmt)).scalar_one_or_none()
        if not order:
            logger.error("apply_refund_success: order missing for refund: %s", refund_no)
            return None

        refund.status = 1
        if wechat_refund_id:
            refund.wechat_refund_id = wechat_refund_id
        if notify_payload:
            refund.notify_payload = notify_payload

        order.refunded_amount = (order.refunded_amount or Decimal("0")) + refund.refund_amount
        order.status = 4

        await self.db.commit()
        await self.db.refresh(refund)
        return refund

    async def apply_refund_failure(
        self, refund_no: str, error_msg: str, notify_payload: str | None,
    ) -> Refund | None:
        """回调失败/异常分支: 仅更新退款记录, 不动订单状态."""
        lock_stmt = select(Refund).where(Refund.refund_no == refund_no).with_for_update()
        refund = (await self.db.execute(lock_stmt)).scalar_one_or_none()
        if not refund:
            logger.warning("apply_refund_failure: refund_no not found: %s", refund_no)
            return None
        if refund.status in (1, 2, 3):
            return refund
        refund.status = 2
        refund.error_msg = error_msg
        if notify_payload:
            refund.notify_payload = notify_payload
        await self.db.commit()
        await self.db.refresh(refund)
        return refund

    async def _mark_refund_failed(self, refund_no: str, error_msg: str) -> None:
        lock_stmt = select(Refund).where(Refund.refund_no == refund_no).with_for_update()
        refund = (await self.db.execute(lock_stmt)).scalar_one_or_none()
        if not refund or refund.status != 0:
            return
        refund.status = 2
        refund.error_msg = error_msg
        await self.db.commit()

    async def _mark_refund_abnormal(
        self, refund_no: str, wechat_refund_id: str | None,
        error_msg: str, notify_payload: str | None,
    ) -> None:
        lock_stmt = select(Refund).where(Refund.refund_no == refund_no).with_for_update()
        refund = (await self.db.execute(lock_stmt)).scalar_one_or_none()
        if not refund or refund.status != 0:
            return
        refund.status = 3
        if wechat_refund_id:
            refund.wechat_refund_id = wechat_refund_id
        refund.error_msg = error_msg
        if notify_payload:
            refund.notify_payload = notify_payload
        await self.db.commit()

    async def _update_refund_wechat_id(self, refund_no: str, wechat_refund_id: str | None) -> None:
        if not wechat_refund_id:
            return
        lock_stmt = select(Refund).where(Refund.refund_no == refund_no).with_for_update()
        refund = (await self.db.execute(lock_stmt)).scalar_one_or_none()
        if not refund:
            return
        refund.wechat_refund_id = wechat_refund_id
        await self.db.commit()

    async def list_refunds(
        self, order_no: str | None, refund_no: str | None,
        status_: int | None, page: int, page_size: int,
    ) -> tuple[list[Refund], int]:
        conditions = []
        if order_no:
            conditions.append(Refund.order_no.ilike(f"%{order_no}%"))
        if refund_no:
            conditions.append(Refund.refund_no.ilike(f"%{refund_no}%"))
        if status_ is not None:
            conditions.append(Refund.status == status_)

        base_query = select(Refund).where(*conditions) if conditions else select(Refund)
        count_stmt = (
            select(func.count(Refund.refund_id)).where(*conditions)
            if conditions else select(func.count(Refund.refund_id))
        )
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = (
            base_query
            .order_by(Refund.refund_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def get_refund_detail(self, refund_id: int) -> Refund | None:
        stmt = select(Refund).where(Refund.refund_id == refund_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_refund_by_no(self, refund_no: str) -> Refund | None:
        stmt = select(Refund).where(Refund.refund_no == refund_no)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def sync_refund_from_wechat(
        self, refund_id: int, pay_svc: WechatPayService,
    ) -> Refund | None:
        """主动从微信查询退款状态并同步本地, 作为回调丢失的兜底."""
        refund = await self.get_refund_detail(refund_id)
        if not refund:
            return None
        if refund.status in (1, 2):
            return refund
        result = await pay_svc.query_refund(refund.refund_no)
        wechat_status = (result.get("status") or "").upper()
        wechat_refund_id = result.get("refund_id")
        payload = _safe_dump(result)
        if wechat_status == "SUCCESS":
            return await self.apply_refund_success(refund.refund_no, wechat_refund_id, payload)
        if wechat_status == "PROCESSING":
            await self._update_refund_wechat_id(refund.refund_no, wechat_refund_id)
            return await self.get_refund_detail(refund_id)
        return await self.apply_refund_failure(
            refund.refund_no, f"WeChat status={wechat_status}", payload,
        )


def _safe_dump(data: dict) -> str:
    import json
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return str(data)
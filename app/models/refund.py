from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.order import Order


class Refund(Base):
    __tablename__ = "refunds"

    refund_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    refund_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="商户退款单号")
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), nullable=False, comment="订单ID")
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="订单号")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="本次退款金额(元)")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="订单原总额(元)")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="退款原因")
    status: Mapped[int] = mapped_column(nullable=False, default=0, comment="退款状态: 0=处理中, 1=成功, 2=失败, 3=异常")
    wechat_refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="微信退款单号")
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="原支付交易号")
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, comment="操作管理员ID")
    channel: Mapped[int] = mapped_column(nullable=False, default=1, comment="退款渠道: 1=微信")
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败/异常原因")
    notify_payload: Mapped[str | None] = mapped_column(Text, nullable=True, comment="微信回调原始数据")
    item_ids: Mapped[str | None] = mapped_column(Text, nullable=True, comment="本次退款关联的订单项ID列表(JSON)")
    disable_result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="兑换码作废结果(JSON)")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    order: Mapped["Order"] = relationship(lazy="selectin")
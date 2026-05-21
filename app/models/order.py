from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="订单号")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, comment="用户ID")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="订单总金额")
    status: Mapped[int] = mapped_column(nullable=False, default=0, comment="订单状态: 0=待支付, 1=已支付, 2=已取消, 3=已完成")
    pay_channel: Mapped[int | None] = mapped_column(nullable=True, comment="支付渠道: 1=微信, 2=支付宝")
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="微信支付交易号")
    pay_info: Mapped[str | None] = mapped_column(Text, nullable=True, comment="微信支付信息JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"

    item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), nullable=False, comment="订单ID")
    sku_id: Mapped[int] = mapped_column(ForeignKey("sku_config.sku_id"), nullable=False, comment="SKU ID")
    exchange_status: Mapped[int] = mapped_column(nullable=False, default=0, comment="兑换状态: 0=未兑换, 1=已兑换")
    exchange_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, comment="兑换用户ID")
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="过期时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    order: Mapped["Order"] = relationship(back_populates="items")
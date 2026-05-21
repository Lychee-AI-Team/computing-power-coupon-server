from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Sku(Base):
    __tablename__ = "sku_config"

    sku_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sku_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="SKU名称")
    face_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="面值")
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0, comment="赠送金额")
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="实际额度")
    status: Mapped[int] = mapped_column(nullable=False, default=1, comment="上下架状态: 0=下架, 1=上架")
    expire_type: Mapped[str] = mapped_column(String(10), nullable=False, default="day", comment="过期时间类型: day=天, month=月, year=年")
    expire_value: Mapped[int] = mapped_column(nullable=False, default=90, comment="过期时间数量")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
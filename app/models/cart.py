from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "sku_id", name="uk_user_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, comment="用户ID")
    sku_id: Mapped[int] = mapped_column(ForeignKey("sku_config.sku_id"), nullable=False, comment="SKU ID")
    quantity: Mapped[int] = mapped_column(nullable=False, default=1, comment="数量")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    sku: Mapped["app.models.sku.Sku"] = relationship(lazy="selectin")

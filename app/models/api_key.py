from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, comment="所属用户ID")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="Key 名称")
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, comment="展示用前缀, sk_+前8位hex")
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="Key SHA256 hex")
    status: Mapped[int] = mapped_column(nullable=False, default=1, comment="状态: 0=禁用, 1=启用")
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="过期时间, NULL=永不过期")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近一次使用时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_user_id", "user_id"),
        Index("idx_status_expired", "status", "expired_at"),
    )

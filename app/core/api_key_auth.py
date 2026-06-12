from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.services.api_key_service import ApiKeyService

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_user_by_api_key(
    raw_key: str | None = Depends(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, ApiKey]:
    """从请求头 X-API-Key 解析并校验 API Key, 返回 (User, ApiKey)."""
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 X-API-Key",
        )

    svc = ApiKeyService(db)
    ak = await svc.get_by_raw_key(raw_key)
    if not ak:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
        )
    if ak.status != 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key 已禁用",
        )
    if ak.expired_at is not None and ak.expired_at <= datetime.now():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key 已过期",
        )

    user = await db.get(User, ak.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key 所属用户不存在",
        )

    await svc.touch_last_used(ak)
    return user, ak

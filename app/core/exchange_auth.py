import hashlib
import hmac
import logging
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

logger = logging.getLogger(__name__)

_exchange_token_header = APIKeyHeader(name="X-Exchange-Token", auto_error=False)


def generate_exchange_token() -> str:
    """根据配置的密钥生成一个永久 token（部署时一次性调用，写入外部平台配置）"""
    if not settings.EXCHANGE_API_SECRET_KEY:
        raise ValueError("EXCHANGE_API_SECRET_KEY is not configured")
    ts = str(int(time.time()))
    sig = hmac.new(
        settings.EXCHANGE_API_SECRET_KEY.encode(),
        ts.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{ts}.{sig}"


def verify_exchange_token(token: str) -> bool:
    """校验 HMAC-SHA256 签名 token，返回是否合法"""
    if not settings.EXCHANGE_API_SECRET_KEY:
        logger.warning("EXCHANGE_API_SECRET_KEY is not configured, rejecting all tokens")
        return False
    if not token or "." not in token:
        return False
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False
    ts_str, sig = parts
    expected = hmac.new(
        settings.EXCHANGE_API_SECRET_KEY.encode(),
        ts_str.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    if settings.EXCHANGE_TOKEN_MAX_AGE_SECONDS > 0:
        try:
            ts = int(ts_str)
        except ValueError:
            return False
        if time.time() - ts > settings.EXCHANGE_TOKEN_MAX_AGE_SECONDS:
            return False
    return True


async def require_exchange_token(token: str = Depends(_exchange_token_header)) -> None:
    if not token or not verify_exchange_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid exchange token",
        )

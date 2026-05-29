from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, decode_access_token
from app.core.redis import get_redis
from app.models.user import User
from app.schemas.user import TokenResponse
from app.services.external_platform import ExternalPlatformService


ROLE_USER_DEFAULT = 1


class UserService:
    def __init__(self, db: AsyncSession, external_service: ExternalPlatformService):
        self.db = db
        self.external_service = external_service

    async def register(self, username: str, password: str) -> tuple[bool, str | None]:
        """委托第三方注册账号。本地 users 表在首次登录时再 upsert。
        返回 (success, error_message)。"""
        ok, message = await self.external_service.register(username, password)
        if not ok:
            return False, message or "Failed to register on external platform"
        return True, None

    async def login(self, username: str, password: str) -> tuple[TokenResponse | None, str | None]:
        """委托第三方校验密码，成功后 upsert 本地 users(id, username) 并签发本地 JWT。"""
        data = await self.external_service.login(username, password)
        if not data:
            return None, "Invalid username or password"

        try:
            user_id = int(data["id"])
        except (TypeError, ValueError, KeyError):
            return None, "Invalid response from external platform"

        ext_username = data.get("username") or username
        role = int(data.get("role", ROLE_USER_DEFAULT))

        local = await self.db.get(User, user_id)
        if local is None:
            local = User(id=user_id, username=ext_username)
            self.db.add(local)
        elif local.username != ext_username:
            local.username = ext_username
        await self.db.commit()

        token = create_access_token({
            "sub": str(user_id),
            "username": ext_username,
            "role": role,
        })
        return TokenResponse(access_token=token), None

    async def search_users(self, keyword: str) -> list[dict]:
        stmt = select(User).where(User.username.ilike(f"%{keyword}%"))
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        return [{"id": u.id, "username": u.username} for u in users]

    async def change_password(self, user: User, new_password: str) -> str | None:
        """使用 admin token 代理第三方修改密码。用户身份由 JWT 决定，不接收前端指定。"""
        ok = await self.external_service.change_password(user.id, user.username, new_password)
        if not ok:
            return "Failed to change password on external platform"
        return None

    async def logout(self, token: str) -> None:
        redis = await get_redis()
        payload = decode_access_token(token)
        if payload and "exp" in payload:
            ttl = int(payload["exp"] - datetime.now(timezone.utc).timestamp())
            if ttl > 0:
                await redis.set(f"token_blacklist:{token}", "1", ex=ttl)

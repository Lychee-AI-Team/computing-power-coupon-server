from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.core.redis import get_redis
from app.models.user import User
from app.schemas.user import UserRegisterRequest, UserRegisterResponse, TokenResponse
from app.services.external_platform import ExternalPlatformService


class UserService:
    def __init__(self, db: AsyncSession, external_service: ExternalPlatformService):
        self.db = db
        self.external_service = external_service

    async def register(self, req: UserRegisterRequest) -> tuple[UserRegisterResponse | None, str | None]:
        existing = await self._get_user_by_username(req.username)
        if existing:
            return None, "User already exists"

        external_user = await self.external_service.search_user(req.username)

        external_user_id = None
        if external_user:
            external_user_id = external_user.get("id")
        else:
            created = await self.external_service.create_user(
                username=req.username,
                password=req.password,
                display_name=req.display_name,
                role=req.role,
            )
            if created is None:
                return None, "Failed to create user on external platform"
            external_user_id = created.get("id")

        user = User(
            username=req.username,
            password=hash_password(req.password),
            display_name=req.display_name,
            role=req.role,
            external_user_id=external_user_id,
        )
        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            return None, "User already exists"
        await self.db.refresh(user)

        return UserRegisterResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,
        ), None

    async def login(self, username: str, password: str) -> tuple[TokenResponse | None, str | None]:
        user = await self._get_user_by_username(username)
        if not user or not verify_password(password, user.password):
            return None, "Invalid username or password"

        token_data = {"sub": str(user.id), "username": user.username, "role": user.role}
        access_token = create_access_token(token_data)

        return TokenResponse(access_token=access_token), None

    async def search_users(self, keyword: str) -> list[dict]:
        stmt = select(User).where(User.username.ilike(f"%{keyword}%"))
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        return [
            {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role}
            for u in users
        ]

    async def _get_user_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def change_password(self, user: User, old_password: str, new_password: str) -> str | None:
        if not verify_password(old_password, user.password):
            return "Old password is incorrect"
        user.password = hash_password(new_password)
        await self.db.commit()
        return None

    async def logout(self, token: str) -> None:
        redis = await get_redis()
        payload = decode_access_token(token)
        if payload and "exp" in payload:
            ttl = int(payload["exp"] - datetime.now(timezone.utc).timestamp())
            if ttl > 0:
                await redis.set(f"token_blacklist:{token}", "1", ex=ttl)

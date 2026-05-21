import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, oauth2_scheme
from app.core.database import get_db
from app.core.external_client import get_external_client
from app.models.user import User
from app.schemas.user import (
    UserRegisterRequest,
    UserRegisterResponse,
    UserLoginRequest,
    TokenResponse,
    UserSearchResponse,
    UserSearchItem,
    ChangePasswordRequest,
    MessageResponse,
)
from app.services.external_platform import ExternalPlatformService
from app.services.user_service import UserService

router = APIRouter(prefix="/api/user", tags=["用户管理"])


def _get_user_service(
    db: AsyncSession = Depends(get_db),
    client: httpx.AsyncClient = Depends(get_external_client),
) -> UserService:
    external_service = ExternalPlatformService(client)
    return UserService(db, external_service)


@router.post("/register", response_model=UserRegisterResponse, status_code=status.HTTP_201_CREATED, summary="用户注册", description="注册新用户账号")
async def register(req: UserRegisterRequest, service: UserService = Depends(_get_user_service)):
    result, error = await service.register(req)
    if error:
        if error == "User already exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error)
    return result


@router.post("/login", response_model=TokenResponse, summary="用户登录", description="用户名密码登录，返回访问令牌")
async def login(req: UserLoginRequest, service: UserService = Depends(_get_user_service)):
    result, error = await service.login(req.username, req.password)
    if error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)
    return result


@router.get("/search", response_model=UserSearchResponse, summary="搜索用户", description="根据关键字搜索用户，支持用户名和显示名模糊匹配")
async def search_user(keyword: str = Query(description="搜索关键字"), service: UserService = Depends(_get_user_service)):
    users = await service.search_users(keyword)
    return UserSearchResponse(users=[UserSearchItem(**u) for u in users])


@router.put("/password", response_model=MessageResponse, summary="修改密码", description="修改当前登录用户的密码")
async def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    service: UserService = Depends(_get_user_service),
):
    error = await service.change_password(user, req.old_password, req.new_password)
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return {"message": "密码修改成功"}


@router.post("/logout", response_model=MessageResponse, summary="用户登出", description="退出登录，使当前令牌失效")
async def logout(token: str = Depends(oauth2_scheme), service: UserService = Depends(_get_user_service)):
    await service.logout(token)
    return {"message": "已成功登出"}

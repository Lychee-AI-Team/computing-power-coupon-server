import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_token_payload, get_current_user, oauth2_scheme, ROLE_USER
from app.core.database import get_db
from app.core.external_client import get_external_client
from app.models.user import User
from app.schemas.user import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserSearchResponse,
    UserSearchItem,
    ChangePasswordRequest,
    CurrentUserResponse,
    MessageResponse,
    WechatQrcodeRequest,
    WechatQrcodeResponse,
    WechatScanStatusResponse,
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


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED, summary="用户注册", description="代理第三方平台完成账号注册")
async def register(req: UserRegisterRequest, service: UserService = Depends(_get_user_service)):
    ok, error = await service.register(req.username, req.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return {"message": "注册成功"}


@router.post("/login", response_model=TokenResponse, summary="用户登录", description="调用第三方平台校验用户名密码，成功后签发本地访问令牌")
async def login(req: UserLoginRequest, service: UserService = Depends(_get_user_service)):
    result, error = await service.login(req.username, req.password)
    if error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)
    return result


@router.get("/search", response_model=UserSearchResponse, summary="搜索用户", description="根据关键字模糊搜索本地用户")
async def search_user(keyword: str = Query(description="搜索关键字"), service: UserService = Depends(_get_user_service)):
    users = await service.search_users(keyword)
    return UserSearchResponse(users=[UserSearchItem(**u) for u in users])


@router.get("/me", response_model=CurrentUserResponse, summary="当前用户信息", description="根据请求头中的访问令牌返回当前登录用户的信息")
async def get_me(
    user: User = Depends(get_current_user),
    payload: dict = Depends(get_current_token_payload),
):
    return CurrentUserResponse(
        id=user.id,
        username=user.username,
        role=int(payload.get("role", ROLE_USER)),
    )


@router.put("/password", response_model=MessageResponse, summary="修改密码", description="代理第三方平台修改当前登录用户的密码")
async def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    service: UserService = Depends(_get_user_service),
):
    error = await service.change_password(user, req.new_password)
    if error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error)
    return {"message": "密码修改成功"}


@router.post("/logout", response_model=MessageResponse, summary="用户登出", description="退出登录，使当前令牌失效")
async def logout(token: str = Depends(oauth2_scheme), service: UserService = Depends(_get_user_service)):
    await service.logout(token)
    return {"message": "已成功登出"}


@router.post("/wechat/qrcode", response_model=WechatQrcodeResponse, summary="微信登录二维码", description="透传第三方平台生成微信登录二维码")
async def wechat_qrcode(req: WechatQrcodeRequest, client: httpx.AsyncClient = Depends(get_external_client)):
    external_service = ExternalPlatformService(client)
    data = await external_service.wechat_qrcode(req.mode)
    if not data:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to generate WeChat QR code")
    return WechatQrcodeResponse(qrcode_url=data["qrcode_url"], scene_str=data["scene_str"])


@router.get("/wechat/scan-status", response_model=WechatScanStatusResponse, summary="微信扫码登录状态", description="轮询微信扫码状态，确认后自动登录并返回 JWT")
async def wechat_scan_status(scene_str: str = Query(title="场景值", description="生成二维码时返回的场景字符串"), service: UserService = Depends(_get_user_service)):
    scan_status, token = await service.wechat_scan_login(scene_str)
    return WechatScanStatusResponse(status=scan_status, access_token=token)

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.api_key import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyInfo,
    ApiKeyListResponse,
    ApiKeyUpdateRequest,
)
from app.schemas.user import MessageResponse
from app.services.api_key_service import _UNSET, ApiKeyService

router = APIRouter(prefix="/api/api-keys", tags=["API Key 管理"])


def _get_service(db: AsyncSession = Depends(get_db)) -> ApiKeyService:
    return ApiKeyService(db)


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 API Key",
    description="为当前登录用户创建一个 API Key, raw_key 仅在响应中返回一次, 请妥善保存",
)
async def create_api_key(
    req: ApiKeyCreateRequest,
    user: User = Depends(get_current_user),
    svc: ApiKeyService = Depends(_get_service),
):
    ak, raw_key = await svc.create(user.id, req.name, req.expired_at)
    return ApiKeyCreateResponse(
        id=ak.id,
        name=ak.name,
        key_prefix=ak.key_prefix,
        status=ak.status,
        expired_at=ak.expired_at,
        last_used_at=ak.last_used_at,
        created_at=ak.created_at,
        updated_at=ak.updated_at,
        raw_key=raw_key,
    )


@router.get(
    "",
    response_model=ApiKeyListResponse,
    summary="API Key 列表",
    description="分页查询当前用户名下的 API Key 列表, 不返回 raw_key",
)
async def list_api_keys(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    user: User = Depends(get_current_user),
    svc: ApiKeyService = Depends(_get_service),
):
    items, total = await svc.list_keys(user.id, page, page_size)
    return ApiKeyListResponse(
        items=[ApiKeyInfo.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.put(
    "/{key_id}",
    response_model=ApiKeyInfo,
    summary="更新 API Key",
    description="更新名称/状态/过期时间; 未传字段保持不变, expired_at 显式传 null 视为重置为永不过期",
)
async def update_api_key(
    req: ApiKeyUpdateRequest,
    key_id: int = Path(..., gt=0, description="API Key ID"),
    user: User = Depends(get_current_user),
    svc: ApiKeyService = Depends(_get_service),
):
    expired_arg = req.expired_at if "expired_at" in req.model_fields_set else _UNSET
    ak = await svc.update(
        key_id, user.id,
        name=req.name, status_=req.status, expired_at=expired_arg,
    )
    if not ak:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    return ApiKeyInfo.model_validate(ak)


@router.delete(
    "/{key_id}",
    response_model=MessageResponse,
    summary="删除 API Key",
    description="物理删除当前用户名下的指定 API Key",
)
async def delete_api_key(
    key_id: int = Path(..., gt=0, description="API Key ID"),
    user: User = Depends(get_current_user),
    svc: ApiKeyService = Depends(_get_service),
):
    ok = await svc.delete(key_id, user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    return {"message": "已删除"}

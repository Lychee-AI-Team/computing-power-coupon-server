from contextlib import asynccontextmanager
import re

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.cart import router as cart_router
from app.api.health import router as health_router
from app.api.order import router as order_router
from app.api.payment import router as payment_router
from app.api.sku import router as sku_router
from app.api.user import router as user_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.external_client import close_external_client, init_external_client
from app.core.redis import close_redis, init_redis


_MULTI_SLASH = re.compile(r"/{2,}")


class NormalizePathMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.scope.get("path", "")
        if "//" in path:
            normalized = _MULTI_SLASH.sub("/", path)
            request.scope["path"] = normalized
            request.scope["raw_path"] = normalized.encode("utf-8")
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    await init_external_client()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_redis()
    await close_external_client()
    await engine.dispose()


app = FastAPI(
    title="算力券服务",
    description="算力券充值与管理系统的 API 文档",
    summary="算力券服务接口",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_DEBUG else None,
)

app.add_middleware(NormalizePathMiddleware)

app.include_router(health_router)
app.include_router(user_router)
app.include_router(sku_router)
app.include_router(order_router)
app.include_router(payment_router)
app.include_router(cart_router)


def _customize_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title,
        summary=getattr(app, "summary", None),
        description=app.description,
        version=app.version,
        routes=app.routes,
    )
    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    if "ValidationError" in schemas:
        schemas["ValidationError"]["title"] = "验证错误"
        schemas["ValidationError"]["description"] = "请求参数验证错误"
        props = schemas["ValidationError"].setdefault("properties", {})
        props.setdefault("loc", {})["title"] = "错误位置"
        props.setdefault("loc", {})["description"] = "错误位置"
        props.setdefault("msg", {})["title"] = "错误信息"
        props.setdefault("msg", {})["description"] = "错误信息"
        props.setdefault("type", {})["title"] = "错误类型"
        props.setdefault("type", {})["description"] = "错误类型"
    if "HTTPValidationError" in schemas:
        schemas["HTTPValidationError"]["title"] = "HTTP验证错误"
        schemas["HTTPValidationError"]["description"] = "HTTP请求参数验证失败"
        props = schemas["HTTPValidationError"].setdefault("properties", {})
        props.setdefault("detail", {})["title"] = "验证错误详情"
        props.setdefault("detail", {})["description"] = "验证错误详情"
    app.openapi_schema = schema
    return schema


app.openapi = _customize_openapi

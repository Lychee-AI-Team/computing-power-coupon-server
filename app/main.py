from contextlib import asynccontextmanager
import logging
import re

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.api_key import router as api_key_router
from app.api.cart import router as cart_router
from app.api.exchange import router as exchange_router
from app.api.external_coupon import router as external_coupon_router
from app.api.external_order import router as external_order_router
from app.api.health import router as health_router
from app.api.order import router as order_router
from app.api.payment import router as payment_router
from app.api.refund import router as refund_router
from app.api.sku import router as sku_router
from app.api.user import router as user_router
from app.core.config import settings
from app.core.database import Base, async_session, engine
from app.core.external_client import (
    close_external_client,
    close_wechat_client,
    get_wechat_client,
    init_external_client,
    init_wechat_client,
)
from app.core.redis import close_redis, init_redis
from app.services.order_service import OrderService
from app.services.wechat_pay_service import WechatPayService

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


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
    await init_wechat_client()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _scheduler.add_job(_cancel_timeout_orders_job, "interval", minutes=1, id="cancel_timeout_orders", replace_existing=True)
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)
    await close_redis()
    await close_external_client()
    await close_wechat_client()
    await engine.dispose()


async def _cancel_timeout_orders_job() -> None:
    try:
        async with async_session() as session:
            svc = OrderService(session)
            pay_svc = WechatPayService(await get_wechat_client())
            count = await svc.cancel_timeout_orders(pay_svc)
            if count:
                logger.info("cancel_timeout_orders: cancelled %d orders", count)
    except Exception as e:
        logger.exception("cancel_timeout_orders_job failed: %s", e)


app = FastAPI(
    title="算力券服务",
    description="算力券充值与管理系统的 API 文档",
    summary="算力券服务接口",
    lifespan=lifespan,
    docs_url=None,
    openapi_url="/openapi.json" if settings.APP_DEBUG else None,
)

app.add_middleware(NormalizePathMiddleware)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>算力券服务 - Swagger UI</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        window.onload = function() {
            SwaggerUIBundle({
                url: window.location.pathname.replace(/\\/docs\\/?$/, '') + '/openapi.json',
                dom_id: '#swagger-ui',
                deepLinking: true,
            });
        };
    </script>
</body>
</html>
"""
    return HTMLResponse(html)

app.include_router(health_router)
app.include_router(user_router)
app.include_router(sku_router)
app.include_router(order_router)
app.include_router(payment_router)
app.include_router(refund_router)
app.include_router(cart_router)
app.include_router(exchange_router)
app.include_router(api_key_router)
app.include_router(external_coupon_router)
app.include_router(external_order_router)


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

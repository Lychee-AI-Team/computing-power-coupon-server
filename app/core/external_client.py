import httpx

from app.core.config import settings

external_client: httpx.AsyncClient | None = None
wechat_client: httpx.AsyncClient | None = None


async def get_external_client() -> httpx.AsyncClient:
    return external_client


async def init_external_client() -> None:
    global external_client
    external_client = httpx.AsyncClient(
        base_url=settings.EXTERNAL_PLATFORM_BASE_URL,
        headers={
            "Authorization": settings.EXTERNAL_PLATFORM_ADMIN_TOKEN,
            "New-Api-User": settings.EXTERNAL_PLATFORM_ADMIN_ID,
        },
        timeout=30.0,
    )


async def close_external_client() -> None:
    global external_client
    if external_client:
        await external_client.aclose()
        external_client = None


async def get_wechat_client() -> httpx.AsyncClient:
    return wechat_client


async def init_wechat_client() -> None:
    global wechat_client
    wechat_client = httpx.AsyncClient(timeout=30.0)


async def close_wechat_client() -> None:
    global wechat_client
    if wechat_client:
        await wechat_client.aclose()
        wechat_client = None

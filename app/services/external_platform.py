import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ExternalPlatformService:
    def __init__(self, client: httpx.AsyncClient):
        """client: 全局共享的 admin client，仅用于需要 admin token 的接口（如改密码、创建兑换码）。
        对于 login/register 这类会被第三方下发 session cookie 的接口，内部会使用一次性 client，
        避免污染全局 client 的 cookie jar 导致后续 admin 调用身份冲突。"""
        self.client = client

    async def login(self, username: str, password: str) -> dict | None:
        """调用第三方登录接口校验密码，成功返回用户基本数据 dict（含 id, username, role 等），失败返回 None。
        使用一次性 client，避免 session cookie 写入全局 admin client。"""
        try:
            async with httpx.AsyncClient(base_url=settings.EXTERNAL_PLATFORM_BASE_URL, timeout=30.0) as client:
                response = await client.post(
                    "/api/user/login",
                    json={"username": username, "password": password},
                )
            response.raise_for_status()
            data = response.json()
            logger.info("external_login response: %s", data)
            if not data.get("success", False):
                return None
            user_data = data.get("data")
            if not isinstance(user_data, dict) or "id" not in user_data:
                return None
            return user_data
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            logger.error("external_login error: %s", e)
            return None

    async def wechat_qrcode(self, mode: str) -> dict | None:
        """调用第三方微信二维码生成接口，成功返回含 qrcode_url, scene_str 的 dict，失败返回 None。
        第三方返回为扁平结构：{success, qrcode_url, scene_str, expire_seconds}。"""
        try:
            async with httpx.AsyncClient(base_url=settings.EXTERNAL_PLATFORM_BASE_URL, timeout=30.0) as client:
                response = await client.post(
                    "/api/wechat/qrcode",
                    json={"mode": mode},
                )
            response.raise_for_status()
            data = response.json()
            logger.info("external_wechat_qrcode response: %s", data)
            if not data.get("success", False):
                return None
            if "qrcode_url" not in data or "scene_str" not in data:
                return None
            return {
                "qrcode_url": data["qrcode_url"],
                "scene_str": data["scene_str"],
                "expire_seconds": data.get("expire_seconds"),
            }
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            logger.error("external_wechat_qrcode error: %s", e)
            return None

    async def wechat_scan_login(self, scene_str: str) -> tuple[str, dict | None]:
        """轮询微信扫码状态。若已确认登录，使用拿到的 session cookie 继续调 /api/user/self 获取用户信息。
        使用一次性 client 维护 cookie jar，避免污染全局 admin client。
        第三方响应为扁平结构：{success, status, message?}。其中 expired 时 success=false。
        返回 (status, user_data)：
          - status: 透传第三方 status 字符串（如 "waiting" | "scanned" | "confirmed" | "expired"），
                    网络或解析异常时为 "error"
          - user_data: 仅在 confirmed 时返回用户信息 dict（含 id, username, role 等）"""
        try:
            async with httpx.AsyncClient(base_url=settings.EXTERNAL_PLATFORM_BASE_URL, timeout=30.0) as client:
                scan_resp = await client.get(
                    "/api/wechat/scan-status",
                    params={"scene_str": scene_str},
                )
                scan_resp.raise_for_status()
                scan_data = scan_resp.json()
                logger.info("external_wechat_scan_status response: %s", scan_data)

                status_value = str(scan_data.get("status", "")).lower()
                if not status_value:
                    return "error", None

                if status_value != "confirmed":
                    return status_value, None

                self_resp = await client.get("/api/user/self")
                self_resp.raise_for_status()
                self_data = self_resp.json()
                logger.info("external_user_self response: %s", self_data)
                if not self_data.get("success", False):
                    return "error", None
                user_data = self_data.get("data")
                if not isinstance(user_data, dict) or "id" not in user_data:
                    return "error", None
                return "confirmed", user_data
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            logger.error("external_wechat_scan_login error: %s", e)
            return "error", None

    async def register(self, username: str, password: str) -> tuple[bool, str]:
        """调用第三方注册接口，返回 (success, message)。使用一次性 client，避免污染全局 client。"""
        try:
            async with httpx.AsyncClient(base_url=settings.EXTERNAL_PLATFORM_BASE_URL, timeout=30.0) as client:
                response = await client.post(
                    "/api/user/register",
                    json={"username": username, "password": password},
                )
            response.raise_for_status()
            data = response.json()
            logger.info("external_register response: %s", data)
            return bool(data.get("success", False)), data.get("message", "")
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            logger.error("external_register error: %s", e)
            return False, "Failed to connect to external platform"

    async def change_password(self, user_id: int, username: str, new_password: str) -> bool:
        """使用 admin token 调用第三方改密码接口。"""
        try:
            response = await self.client.put(
                "/api/user/",
                json={"id": user_id, "username": username, "password": new_password},
            )
            response.raise_for_status()
            data = response.json()
            return bool(data.get("success", False))
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            logger.error("external_change_password error: %s", e)
            return False

    async def get_user(self, user_id: int) -> dict | None:
        """使用 admin token 获取第三方用户信息。存在返回 data dict（含 id, username, ...），不存在或错误返回 None。"""
        try:
            response = await self.client.get(f"/api/user/{user_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            if not data.get("success", False):
                return None
            user_data = data.get("data")
            if not isinstance(user_data, dict) or "id" not in user_data:
                return None
            return user_data
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            logger.error("external_get_user error: user_id=%s err=%s", user_id, e)
            return None

    async def create_redemption(
        self, name: str, quota: int, count: int = 1, expired_time: int = 0
    ) -> list[str] | None:
        try:
            response = await self.client.post(
                "/api/redemption/",
                json={
                    "name": name,
                    "quota": quota,
                    "count": count,
                    "expired_time": expired_time,
                },
            )
            response.raise_for_status()
            data = response.json()
            logger.info("create_redemption response: %s", data)
            if data.get("success", False):
                return data.get("data", [])
            logger.warning("create_redemption failed: %s", data.get("message", ""))
            return None
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            logger.error("create_redemption error: %s", e)
            return None

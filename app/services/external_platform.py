import logging

import httpx

logger = logging.getLogger(__name__)


class ExternalPlatformService:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def search_user(self, username: str) -> dict | None:
        try:
            response = await self.client.get("/api/user/search", params={"keyword": username})
            response.raise_for_status()
            data = response.json()
            logger.info("search_user response: %s", data)
            result = data.get("data", {})
            users = result.get("items", []) if isinstance(result, dict) else result if isinstance(result, list) else []
            if isinstance(users, list) and len(users) > 0:
                for user in users:
                    if user.get("username") == username:
                        return user
                return users[0]
            return None
        except (httpx.HTTPStatusError, httpx.RequestError, KeyError, ValueError) as e:
            logger.error("search_user error: %s", e)
            return None

    async def create_user(self, username: str, password: str, display_name: str, role: int) -> dict | None:
        try:
            response = await self.client.post(
                "/api/user/",
                json={
                    "username": username,
                    "password": password,
                    "display_name": display_name,
                    "role": role,
                },
            )
            response.raise_for_status()
            data = response.json()
            logger.info("create_user response: %s", data)
            if data.get("success", False):
                return data.get("data", {"username": username, "display_name": display_name, "role": role})
            return None
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            logger.error("create_user error: %s", e)
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

from redis.asyncio import Redis

from app.core.config import settings

redis: Redis | None = None


async def get_redis() -> Redis:
    return redis


async def init_redis() -> None:
    global redis
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()


async def close_redis() -> None:
    global redis
    if redis:
        await redis.aclose()
        redis = None

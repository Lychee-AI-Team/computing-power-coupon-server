from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core.redis import get_redis
from app.schemas.health import HealthResponse

router = APIRouter(tags=["健康检查"])


@router.get("/health", response_model=HealthResponse, summary="健康检查", description="检查服务及 Redis 连接是否正常")
async def health_check(redis: Redis = Depends(get_redis)):
    await redis.ping()
    return {"status": "ok"}

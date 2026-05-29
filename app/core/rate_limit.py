from fastapi import HTTPException, status

from app.core.redis import get_redis

_LUA_INCR_EXPIRE = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


async def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    """Redis 固定窗口计数器限流，INCR+EXPIRE 用 Lua 脚本保证原子性，超限抛出 HTTP 429"""
    redis = await get_redis()
    current = await redis.eval(_LUA_INCR_EXPIRE, 1, key, window_seconds)
    if int(current) > max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后再试",
        )

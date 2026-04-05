import redis.asyncio as aioredis

from app.config import settings

redis_pool: aioredis.Redis | None = None


async def init_redis():
    global redis_pool
    redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )


async def close_redis():
    global redis_pool
    if redis_pool:
        await redis_pool.close()


async def get_redis() -> aioredis.Redis:
    if redis_pool is None:
        raise RuntimeError("Redis not initialized")
    return redis_pool

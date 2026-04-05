import redis.asyncio as aioredis
from fastapi import HTTPException


async def acquire_lock(redis: aioredis.Redis, key: str, ttl_seconds: int = 3) -> bool:
    """Attempt to acquire a distributed lock. Returns True if successful."""
    result = await redis.set(key, "1", ex=ttl_seconds, nx=True)
    return result is not None


async def release_lock(redis: aioredis.Redis, key: str):
    """Release a distributed lock."""
    await redis.delete(key)

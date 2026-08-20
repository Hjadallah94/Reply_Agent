from functools import lru_cache

import redis
import redis.asyncio as redis_async

from reply_agent.config import get_settings


@lru_cache
def get_redis_sync() -> redis.Redis:
    """Used by RQ, which requires a sync redis-py client."""
    return redis.Redis.from_url(get_settings().redis_url)


@lru_cache
def get_redis_async() -> redis_async.Redis:
    """Used for the webhook-layer dedup check (Doc 2 Section 2.1)."""
    return redis_async.Redis.from_url(get_settings().redis_url)

"""
Async Redis client for:
- Dashboard cache (hot path)
- Debouncing windows
- Pub/Sub for real-time WebSocket events
- Time series aggregations
"""

import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None
_pubsub_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Get or create the Redis client."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
        )
    return _redis


async def get_pubsub_redis() -> aioredis.Redis:
    """Separate Redis client for Pub/Sub."""
    global _pubsub_redis
    if _pubsub_redis is None:
        _pubsub_redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _pubsub_redis


async def close_redis():
    """Close Redis connections."""
    global _redis, _pubsub_redis
    if _redis:
        await _redis.close()
        _redis = None
    if _pubsub_redis:
        await _pubsub_redis.close()
        _pubsub_redis = None


# ── Dashboard Cache Operations ──────────────────────────────────────────

async def cache_dashboard_stats(stats: dict):
    """Cache aggregated dashboard stats."""
    r = await get_redis()
    await r.set("dashboard:stats", json.dumps(stats), ex=10)


async def get_dashboard_stats() -> Optional[dict]:
    """Get cached dashboard stats."""
    r = await get_redis()
    data = await r.get("dashboard:stats")
    return json.loads(data) if data else None


async def cache_work_item(work_item_id: str, data: dict):
    """Cache a work item for hot-path reads."""
    r = await get_redis()
    await r.set(f"workitem:{work_item_id}", json.dumps(data), ex=60)


async def get_cached_work_item(work_item_id: str) -> Optional[dict]:
    """Get cached work item."""
    r = await get_redis()
    data = await r.get(f"workitem:{work_item_id}")
    return json.loads(data) if data else None


async def invalidate_work_item_cache(work_item_id: str):
    """Invalidate cached work item."""
    r = await get_redis()
    await r.delete(f"workitem:{work_item_id}")


# ── Debounce Operations ─────────────────────────────────────────────────

async def add_to_debounce_window(component_id: str, signal_id: str, timestamp: float) -> int:
    """
    Add a signal to the debounce window for a component.
    Returns the current count of signals in the window.
    Uses Redis sorted set with timestamp as score.
    """
    r = await get_redis()
    key = f"debounce:{component_id}"
    window = settings.DEBOUNCE_WINDOW_SEC

    pipe = r.pipeline()
    # Remove expired entries
    pipe.zremrangebyscore(key, "-inf", timestamp - window)
    # Add the new signal
    pipe.zadd(key, {signal_id: timestamp})
    # Get current window count
    pipe.zcard(key)
    # Set expiry on the key
    pipe.expire(key, window * 2)
    results = await pipe.execute()

    return results[2]  # zcard result


async def get_debounce_signal_ids(component_id: str) -> list[str]:
    """Get all signal IDs in the current debounce window."""
    r = await get_redis()
    key = f"debounce:{component_id}"
    return await r.zrange(key, 0, -1)


async def clear_debounce_window(component_id: str):
    """Clear the debounce window after creating a work item."""
    r = await get_redis()
    await r.delete(f"debounce:{component_id}")


# ── Pub/Sub for Real-time Events ────────────────────────────────────────

async def publish_event(channel: str, data: dict):
    """Publish an event to a Redis channel."""
    r = await get_redis()
    await r.publish(channel, json.dumps(data))


# ── Time Series Tracking ────────────────────────────────────────────────

async def increment_signal_counter():
    """Increment the signal ingestion counter for time series tracking."""
    r = await get_redis()
    pipe = r.pipeline()
    pipe.incr("metrics:signals_total")
    pipe.incr("metrics:signals_window")
    await pipe.execute()


async def get_and_reset_signal_window() -> int:
    """Get the signals count for the current window and reset."""
    r = await get_redis()
    count = await r.getset("metrics:signals_window", "0")
    return int(count) if count else 0


async def get_total_signals() -> int:
    """Get total signals ingested."""
    r = await get_redis()
    count = await r.get("metrics:signals_total")
    return int(count) if count else 0


async def record_timeseries_point(metric: str, value: float, timestamp: float):
    """Record a time series data point using sorted sets."""
    r = await get_redis()
    key = f"ts:{metric}"
    data = json.dumps({"value": value, "ts": timestamp})
    await r.zadd(key, {data: timestamp})
    # Keep only last hour of data
    await r.zremrangebyscore(key, "-inf", timestamp - 3600)


async def get_timeseries(metric: str, start: float, end: float) -> list[dict]:
    """Get time series data points in range."""
    r = await get_redis()
    key = f"ts:{metric}"
    entries = await r.zrangebyscore(key, start, end)
    return [json.loads(e) for e in entries]

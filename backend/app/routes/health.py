"""
Health check and dashboard API routes.
"""

import logging
import time

from fastapi import APIRouter, Query

from app.db import postgres as pg
from app.db import redis_client
from app.services.metrics import metrics_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """
    Health endpoint — returns service health, DB connectivity,
    queue depth, and throughput metrics.
    """
    return await metrics_service.get_health()


dashboard_router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@dashboard_router.get("/stats")
async def get_dashboard_stats():
    """
    Get aggregated dashboard statistics.
    Reads from Redis cache (hot path) to avoid querying PostgreSQL for every refresh.
    """
    # Try cache first
    cached = await redis_client.get_dashboard_stats()
    if cached:
        return cached

    # Compute fresh stats from PostgreSQL
    stats = {}

    # Work item counts by state
    rows = await pg.fetch_with_retry(
        "SELECT state, COUNT(*) as count FROM work_items GROUP BY state"
    )
    state_counts = {row["state"]: row["count"] for row in rows}
    stats["by_state"] = {
        "OPEN": state_counts.get("OPEN", 0),
        "INVESTIGATING": state_counts.get("INVESTIGATING", 0),
        "RESOLVED": state_counts.get("RESOLVED", 0),
        "CLOSED": state_counts.get("CLOSED", 0),
    }
    stats["total_incidents"] = sum(state_counts.values())
    stats["active_incidents"] = (
        state_counts.get("OPEN", 0) + state_counts.get("INVESTIGATING", 0)
    )

    # By severity
    rows = await pg.fetch_with_retry(
        "SELECT severity, COUNT(*) as count FROM work_items WHERE state != 'CLOSED' GROUP BY severity"
    )
    stats["by_severity"] = {row["severity"]: row["count"] for row in rows}

    # Average MTTR (for closed items with RCA)
    row = await pg.fetchrow_with_retry(
        "SELECT AVG(mttr_seconds) as avg_mttr FROM work_items WHERE mttr_seconds IS NOT NULL"
    )
    avg_mttr = row["avg_mttr"] if row and row["avg_mttr"] else 0
    stats["avg_mttr_seconds"] = round(float(avg_mttr), 1)
    stats["avg_mttr_formatted"] = f"{float(avg_mttr)/60:.1f} min" if avg_mttr else "N/A"

    # Total signals
    total_signals = await redis_client.get_total_signals()
    stats["total_signals"] = total_signals

    # Throughput
    stats["current_throughput"] = metrics_service.last_signals_per_sec

    # Cache stats
    await redis_client.cache_dashboard_stats(stats)

    return stats


@dashboard_router.get("/timeseries")
async def get_timeseries(
    metric: str = Query("signals_per_sec", description="Metric name"),
    duration_minutes: int = Query(60, le=360, description="Duration in minutes"),
):
    """Get time series data for charts."""
    now = time.time()
    start = now - (duration_minutes * 60)
    data = await redis_client.get_timeseries(metric, start, now)
    return {
        "metric": metric,
        "data": data,
        "duration_minutes": duration_minutes,
    }

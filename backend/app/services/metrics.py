"""
Observability service — tracks throughput metrics and prints to console.
Prints signals/sec every 5 seconds as required.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from app.config import settings
from app.db import redis_client

logger = logging.getLogger(__name__)


class MetricsService:
    """Tracks and reports system throughput metrics."""

    def __init__(self):
        self._running = False
        self._task = None
        self.start_time = time.monotonic()
        self.last_signals_per_sec = 0.0

    async def start(self):
        """Start the metrics reporting loop."""
        self._running = True
        self._task = asyncio.create_task(self._report_loop())
        logger.info(f"Metrics service started (interval: {settings.METRICS_INTERVAL_SEC}s)")

    async def stop(self):
        """Stop the metrics reporting loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _report_loop(self):
        """Print throughput metrics to console every N seconds."""
        while self._running:
            try:
                await asyncio.sleep(settings.METRICS_INTERVAL_SEC)

                # Get window signal count and reset
                window_count = await redis_client.get_and_reset_signal_window()
                total_count = await redis_client.get_total_signals()
                signals_per_sec = window_count / settings.METRICS_INTERVAL_SEC
                self.last_signals_per_sec = signals_per_sec

                # Record time series data point
                now = time.time()
                await redis_client.record_timeseries_point(
                    "signals_per_sec", signals_per_sec, now
                )

                # Get queue metrics
                from app.ingestion.queue import signal_queue
                queue_metrics = signal_queue.get_metrics()

                # Get rate limiter metrics
                from app.ingestion.rate_limiter import rate_limiter
                rl_metrics = rate_limiter.get_metrics()

                # Print metrics
                uptime = time.monotonic() - self.start_time
                print(
                    f"\n{'='*60}\n"
                    f"IMS Metrics Report | {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC\n"
                    f"{'─'*60}\n"
                    f"  Throughput:     {signals_per_sec:.1f} signals/sec\n"
                    f"  Total Signals:  {total_count:,}\n"
                    f"  Queue:          {queue_metrics['queue_size']:,}/{queue_metrics['queue_capacity']:,} "
                    f"({queue_metrics['queue_utilization_pct']:.1f}%)\n"
                    f"  Processed:      {queue_metrics['total_processed']:,}\n"
                    f"  Dropped:        {queue_metrics['total_dropped']:,}\n"
                    f"  Rate Limited:   {rl_metrics['total_rejected']:,}\n"
                    f"  Uptime:         {uptime:.0f}s\n"
                    f"{'='*60}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics error: {e}")

    async def get_health(self) -> dict:
        """Get full health status for /health endpoint."""
        from app.ingestion.queue import signal_queue
        from app.ingestion.rate_limiter import rate_limiter

        # Check database connectivity
        db_health = {}

        # PostgreSQL
        try:
            from app.db.postgres import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            db_health["postgres"] = "healthy"
        except Exception as e:
            db_health["postgres"] = f"unhealthy: {e}"

        # MongoDB
        try:
            from app.db.mongodb import get_client
            client = get_client()
            await client.admin.command("ping")
            db_health["mongodb"] = "healthy"
        except Exception as e:
            db_health["mongodb"] = f"unhealthy: {e}"

        # Redis
        try:
            r = await redis_client.get_redis()
            await r.ping()
            db_health["redis"] = "healthy"
        except Exception as e:
            db_health["redis"] = f"unhealthy: {e}"

        total_signals = await redis_client.get_total_signals()

        return {
            "status": "healthy" if all(
                v == "healthy" for v in db_health.values()
            ) else "degraded",
            "uptime_seconds": round(time.monotonic() - self.start_time, 1),
            "databases": db_health,
            "throughput": {
                "signals_per_sec": self.last_signals_per_sec,
                "total_signals": total_signals,
            },
            "queue": signal_queue.get_metrics(),
            "rate_limiter": rate_limiter.get_metrics(),
        }


# Singleton
metrics_service = MetricsService()

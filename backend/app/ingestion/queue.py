"""
Async backpressure queue for signal ingestion.
Bounded queue prevents OOM under burst conditions.
Returns 503 when full, signaling producers to back off.
"""

import asyncio
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class BackpressureQueue:
    """
    Bounded async queue that separates signal ingestion (producer)
    from processing (consumer). This is the core backpressure mechanism:
    - If persistence layer is slow, queue buffers signals in memory
    - If queue is full (burst > capacity), returns 503 to producer
    - Workers drain the queue concurrently
    """

    def __init__(self, maxsize: int = None):
        self.maxsize = maxsize or settings.BACKPRESSURE_QUEUE_SIZE
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=self.maxsize)
        self._workers: list[asyncio.Task] = []
        self._processor = None
        self._running = False

        # Metrics
        self.total_enqueued = 0
        self.total_processed = 0
        self.total_dropped = 0

    async def enqueue(self, item: Any) -> bool:
        """
        Try to enqueue a signal for processing.
        Returns True if successful, False if queue is full (backpressure).
        Non-blocking to keep API response times low.
        """
        try:
            self._queue.put_nowait(item)
            self.total_enqueued += 1
            return True
        except asyncio.QueueFull:
            self.total_dropped += 1
            logger.warning(
                f"Backpressure: queue full ({self.maxsize}), signal dropped. "
                f"Total dropped: {self.total_dropped}"
            )
            return False

    async def start_workers(self, processor_func, worker_count: int = None):
        """Start consumer worker tasks."""
        self._processor = processor_func
        self._running = True
        count = worker_count or settings.WORKER_COUNT

        for i in range(count):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)

        logger.info(f"Started {count} queue workers (capacity: {self.maxsize})")

    async def _worker(self, worker_id: int):
        """Worker coroutine that processes signals from the queue."""
        logger.info(f"Worker-{worker_id} started")
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                try:
                    await self._processor(item)
                    self.total_processed += 1
                except Exception as e:
                    logger.error(f"Worker-{worker_id} processing error: {e}")
                finally:
                    self._queue.task_done()
            except asyncio.TimeoutError:
                continue  # Check if still running
            except asyncio.CancelledError:
                break

        logger.info(f"Worker-{worker_id} stopped")

    async def stop(self):
        """Stop all workers gracefully."""
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("All queue workers stopped")

    def get_metrics(self) -> dict:
        """Return queue metrics."""
        return {
            "queue_size": self._queue.qsize(),
            "queue_capacity": self.maxsize,
            "queue_utilization_pct": round(
                (self._queue.qsize() / self.maxsize) * 100, 2
            ) if self.maxsize > 0 else 0,
            "total_enqueued": self.total_enqueued,
            "total_processed": self.total_processed,
            "total_dropped": self.total_dropped,
        }


# Singleton instance
signal_queue = BackpressureQueue()

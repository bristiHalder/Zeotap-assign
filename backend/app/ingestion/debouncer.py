"""
Redis-based signal debouncer.
If 100+ signals arrive for the same Component ID within 10 seconds,
only ONE Work Item is created while all signals are linked to it.
"""

import logging
from datetime import datetime, timezone

from app.config import settings
from app.db import redis_client
from app.db import postgres as pg
from app.db import mongodb as mongo
from app.models.signal import Signal
from app.models.workitem import WorkItem

logger = logging.getLogger(__name__)


class Debouncer:
    """
    Debouncing logic using Redis sorted sets.

    For each component_id, we maintain a sliding window:
    - Key: debounce:{component_id}
    - Members: signal_ids scored by timestamp
    - When count >= threshold, create ONE work item and link all signals
    """

    def __init__(self):
        self.threshold = settings.DEBOUNCE_THRESHOLD
        self.window_sec = settings.DEBOUNCE_WINDOW_SEC

    async def process_signal(self, signal: Signal) -> dict:
        """
        Process a signal through the debounce logic.

        Returns:
            dict with keys:
                - action: "debounced" | "buffered" | "created"
                - work_item_id: str or None
        """
        timestamp = signal.timestamp.timestamp()

        # Add to debounce window
        count = await redis_client.add_to_debounce_window(
            signal.component_id, signal.signal_id, timestamp
        )

        logger.debug(
            f"Debounce: {signal.component_id} count={count}/{self.threshold}"
        )

        if count >= self.threshold:
            # Threshold reached — create work item
            work_item = await self._create_work_item(signal, count)

            # Link all buffered signals to the work item
            signal_ids = await redis_client.get_debounce_signal_ids(signal.component_id)
            await self._link_signals_to_work_item(signal_ids, work_item.id)

            # Clear the debounce window
            await redis_client.clear_debounce_window(signal.component_id)

            # Publish event for real-time dashboard
            await redis_client.publish_event("incidents", {
                "type": "new_incident",
                "work_item": work_item.model_dump(mode="json"),
            })

            logger.info(
                f"Debounce triggered for {signal.component_id}: "
                f"created work item {work_item.id} with {count} signals"
            )

            return {"action": "created", "work_item_id": work_item.id}

        elif count == 1:
            # First signal — might not reach threshold; still create a work item
            # (for single signals, we create immediately for visibility)
            work_item = await self._create_work_item(signal, 1)
            await self._link_signals_to_work_item([signal.signal_id], work_item.id)

            await redis_client.publish_event("incidents", {
                "type": "new_incident",
                "work_item": work_item.model_dump(mode="json"),
            })

            return {"action": "created", "work_item_id": work_item.id}

        else:
            # Signal is buffered — waiting for threshold or new work item exists
            # Try to find existing work item for this component
            row = await pg.fetchrow_with_retry(
                """SELECT id, signal_count FROM work_items
                   WHERE component_id = $1 AND state != 'CLOSED'
                   ORDER BY created_at DESC LIMIT 1""",
                signal.component_id,
            )
            if row:
                # Update signal count on existing work item
                await pg.execute_with_retry(
                    """UPDATE work_items SET signal_count = signal_count + 1,
                       updated_at = NOW() WHERE id = $1""",
                    row["id"],
                )
                # Link this signal
                await self._link_signals_to_work_item([signal.signal_id], row["id"])
                await redis_client.invalidate_work_item_cache(row["id"])

                return {"action": "debounced", "work_item_id": row["id"]}

            return {"action": "buffered", "work_item_id": None}

    async def _create_work_item(self, signal: Signal, signal_count: int) -> WorkItem:
        """Create a new work item in PostgreSQL."""
        work_item = WorkItem(
            component_id=signal.component_id,
            component_type=signal.component_type.value,
            severity=signal.severity.value,
            signal_count=signal_count,
            first_signal_time=signal.timestamp,
        )
        work_item.title = work_item.generate_title()

        await pg.execute_with_retry(
            """INSERT INTO work_items
               (id, component_id, component_type, severity, state, signal_count,
                title, created_at, updated_at, first_signal_time)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
               ON CONFLICT (id) DO NOTHING""",
            work_item.id,
            work_item.component_id,
            work_item.component_type,
            work_item.severity,
            work_item.state.value,
            work_item.signal_count,
            work_item.title,
            work_item.created_at,
            work_item.updated_at,
            work_item.first_signal_time,
        )

        # Cache for hot-path reads
        await redis_client.cache_work_item(
            work_item.id, work_item.model_dump(mode="json")
        )

        return work_item

    async def _link_signals_to_work_item(self, signal_ids: list[str], work_item_id: str):
        """Link signals to a work item in MongoDB."""
        db = mongo.get_database()
        if signal_ids:
            await db["signals"].update_many(
                {"_id": {"$in": signal_ids}},
                {"$set": {"work_item_id": work_item_id}},
            )


# Singleton
debouncer = Debouncer()

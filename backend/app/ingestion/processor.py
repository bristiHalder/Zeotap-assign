"""
Signal processing pipeline.
Orchestrates: MongoDB storage → Debounce check → Work item creation → Cache update.
"""

import logging

from app.db import mongodb as mongo
from app.db import redis_client
from app.ingestion.debouncer import debouncer
from app.models.signal import Signal
from app.workflow.alerting import alert_engine

logger = logging.getLogger(__name__)


async def process_signal(signal: Signal):
    """
    Full signal processing pipeline:
    1. Store raw signal in MongoDB (audit log / data lake)
    2. Increment metrics counter
    3. Run debounce logic
    4. Trigger alerting strategy if new work item created
    """
    try:
        # 1. Store raw signal in MongoDB (Data Lake)
        await mongo.insert_with_retry("signals", signal.to_mongo())

        # 2. Increment metrics
        await redis_client.increment_signal_counter()

        # 3. Debounce and potentially create work item
        result = await debouncer.process_signal(signal)

        # 4. If a new work item was created, trigger alerting
        if result["action"] == "created" and result["work_item_id"]:
            await alert_engine.trigger_alert(signal)

        logger.debug(
            f"Processed signal {signal.signal_id}: "
            f"action={result['action']}, work_item={result.get('work_item_id')}"
        )

    except Exception as e:
        logger.error(f"Error processing signal {signal.signal_id}: {e}")
        raise

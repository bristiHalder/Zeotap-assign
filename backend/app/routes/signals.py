"""
Signal ingestion API routes.
Supports single and batch signal ingestion with rate limiting and backpressure.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from app.ingestion.rate_limiter import rate_limiter
from app.ingestion.queue import signal_queue
from app.models.signal import Signal, SignalIn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def ingest_signal(signal_in: SignalIn):
    """
    Ingest a single signal.
    Returns 202 Accepted (async processing).
    Returns 429 if rate-limited.
    Returns 503 if backpressure queue is full.
    """
    # Rate limit check
    if not await rate_limiter.acquire():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please reduce signal frequency.",
        )

    # Create full signal from input
    signal = Signal.from_input(signal_in)

    # Enqueue for async processing (backpressure)
    if not await signal_queue.enqueue(signal):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System under heavy load. Signal queue is full. Please retry later.",
        )

    return {
        "status": "accepted",
        "signal_id": signal.signal_id,
        "message": "Signal queued for processing",
    }


@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
async def ingest_batch(signals: list[SignalIn]):
    """
    Ingest a batch of signals (up to 1000).
    Returns partial success if some signals are dropped due to backpressure.
    """
    if len(signals) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size cannot exceed 1000 signals.",
        )

    # Rate limit check (1 token per signal)
    accepted = []
    rejected = []

    for signal_in in signals:
        if not await rate_limiter.acquire():
            rejected.append({"component_id": signal_in.component_id, "reason": "rate_limited"})
            continue

        signal = Signal.from_input(signal_in)
        if await signal_queue.enqueue(signal):
            accepted.append(signal.signal_id)
        else:
            rejected.append({"component_id": signal_in.component_id, "reason": "queue_full"})

    return {
        "status": "partial" if rejected else "accepted",
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_ids": accepted[:10],  # Return first 10 for brevity
        "rejected": rejected[:10],
    }

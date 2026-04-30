"""
RCA (Root Cause Analysis) API routes.
Enforces mandatory RCA for work item closure.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.db import postgres as pg
from app.db import redis_client
from app.models.rca import RCA, RCACreate
from app.models.workitem import WorkItemState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workitems", tags=["rca"])


def _row_to_dict(row) -> dict:
    """Convert asyncpg Record to JSON-serializable dict."""
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = v.isoformat()
    return d


@router.post("/{work_item_id}/rca", status_code=status.HTTP_201_CREATED)
async def submit_rca(work_item_id: str, rca_in: RCACreate):
    """
    Submit an RCA for a work item.
    Validates completeness and calculates MTTR.
    Must be submitted before work item can be CLOSED.
    """
    # Verify work item exists
    row = await pg.fetchrow_with_retry(
        "SELECT * FROM work_items WHERE id = $1", work_item_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Work item not found")

    # Check if RCA already exists
    existing = await pg.fetchrow_with_retry(
        "SELECT id FROM rca_records WHERE work_item_id = $1", work_item_id
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="RCA already exists for this work item. Use PUT to update.",
        )

    # Create RCA with MTTR calculation
    rca = RCA.from_create(work_item_id, rca_in)

    # Store in PostgreSQL (transactional)
    pool = await pg.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO rca_records
                   (id, work_item_id, incident_start, incident_end,
                    root_cause_category, root_cause_description,
                    fix_applied, prevention_steps, mttr_seconds, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                rca.id,
                work_item_id,
                rca.incident_start,
                rca.incident_end,
                rca.root_cause_category.value,
                rca.root_cause_description,
                rca.fix_applied,
                rca.prevention_steps,
                rca.mttr_seconds,
                datetime.now(timezone.utc),
            )

            # Update work item MTTR
            await conn.execute(
                "UPDATE work_items SET mttr_seconds = $1, updated_at = NOW() WHERE id = $2",
                rca.mttr_seconds, work_item_id,
            )

    # Invalidate cache
    await redis_client.invalidate_work_item_cache(work_item_id)

    # Publish event
    await redis_client.publish_event("incidents", {
        "type": "rca_submitted",
        "work_item_id": work_item_id,
        "mttr_seconds": rca.mttr_seconds,
    })

    logger.info(
        f"RCA submitted for work item {work_item_id}: "
        f"MTTR={rca.mttr_seconds:.0f}s ({rca.mttr_seconds/60:.1f}m)"
    )

    return {
        "status": "created",
        "rca": rca.model_dump(mode="json"),
        "mttr_seconds": rca.mttr_seconds,
        "mttr_formatted": f"{rca.mttr_seconds/60:.1f} minutes",
    }


@router.get("/{work_item_id}/rca")
async def get_rca(work_item_id: str):
    """Get the RCA for a work item."""
    row = await pg.fetchrow_with_retry(
        "SELECT * FROM rca_records WHERE work_item_id = $1", work_item_id
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No RCA found for this work item",
        )

    return _row_to_dict(row)


@router.put("/{work_item_id}/rca")
async def update_rca(work_item_id: str, rca_in: RCACreate):
    """Update an existing RCA."""
    existing = await pg.fetchrow_with_retry(
        "SELECT id FROM rca_records WHERE work_item_id = $1", work_item_id
    )
    if not existing:
        raise HTTPException(status_code=404, detail="No RCA found to update")

    rca = RCA.from_create(work_item_id, rca_in)
    rca.id = existing["id"]

    await pg.execute_with_retry(
        """UPDATE rca_records SET
           incident_start = $1, incident_end = $2,
           root_cause_category = $3, root_cause_description = $4,
           fix_applied = $5, prevention_steps = $6, mttr_seconds = $7
           WHERE work_item_id = $8""",
        rca.incident_start, rca.incident_end,
        rca.root_cause_category.value, rca.root_cause_description,
        rca.fix_applied, rca.prevention_steps, rca.mttr_seconds,
        work_item_id,
    )

    # Update MTTR on work item too
    await pg.execute_with_retry(
        "UPDATE work_items SET mttr_seconds = $1, updated_at = NOW() WHERE id = $2",
        rca.mttr_seconds, work_item_id,
    )

    await redis_client.invalidate_work_item_cache(work_item_id)

    return {
        "status": "updated",
        "rca": rca.model_dump(mode="json"),
        "mttr_seconds": rca.mttr_seconds,
    }

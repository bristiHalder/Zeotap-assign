"""
Work item management API routes.
CRUD + state transitions with workflow engine integration.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.db import postgres as pg
from app.db import redis_client
from app.db import mongodb as mongo
from app.models.workitem import WorkItemState, WorkItemTransition
from app.workflow.state_machine import (
    state_machine,
    InvalidTransitionError,
    RCARequiredError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workitems", tags=["workitems"])


def _row_to_dict(row) -> dict:
    """Convert asyncpg Record to JSON-serializable dict."""
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = v.isoformat()
    return d


@router.get("/")
async def list_work_items(
    state: Optional[str] = Query(None, description="Filter by state"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    component_type: Optional[str] = Query(None, description="Filter by component type"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """List work items with optional filters, sorted by severity then created_at."""
    query = "SELECT * FROM work_items WHERE 1=1"
    params = []
    param_idx = 1

    if state:
        query += f" AND state = ${param_idx}"
        params.append(state)
        param_idx += 1

    if severity:
        query += f" AND severity = ${param_idx}"
        params.append(severity)
        param_idx += 1

    if component_type:
        query += f" AND component_type = ${param_idx}"
        params.append(component_type)
        param_idx += 1

    # Sort by severity priority (P0 first), then by creation time
    query += """
        ORDER BY
            CASE severity
                WHEN 'P0' THEN 0
                WHEN 'P1' THEN 1
                WHEN 'P2' THEN 2
                WHEN 'P3' THEN 3
            END,
            created_at DESC
    """
    query += f" LIMIT ${param_idx} OFFSET ${param_idx + 1}"
    params.extend([limit, offset])

    rows = await pg.fetch_with_retry(query, *params)

    # Get total count
    count_query = "SELECT COUNT(*) FROM work_items WHERE 1=1"
    count_params = []
    cparam_idx = 1
    if state:
        count_query += f" AND state = ${cparam_idx}"
        count_params.append(state)
        cparam_idx += 1
    if severity:
        count_query += f" AND severity = ${cparam_idx}"
        count_params.append(severity)
        cparam_idx += 1
    if component_type:
        count_query += f" AND component_type = ${cparam_idx}"
        count_params.append(component_type)
        cparam_idx += 1

    count_row = await pg.fetchrow_with_retry(count_query, *count_params)
    total = count_row["count"] if count_row else 0

    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{work_item_id}")
async def get_work_item(work_item_id: str):
    """Get a single work item with its details."""
    # Try cache first (hot path)
    cached = await redis_client.get_cached_work_item(work_item_id)
    if cached:
        return cached

    row = await pg.fetchrow_with_retry(
        "SELECT * FROM work_items WHERE id = $1", work_item_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Work item not found")

    data = _row_to_dict(row)

    # Cache for subsequent reads
    await redis_client.cache_work_item(work_item_id, data)

    return data


@router.get("/{work_item_id}/signals")
async def get_work_item_signals(
    work_item_id: str,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """Get raw signals linked to a work item (from MongoDB data lake)."""
    db = mongo.get_database()
    cursor = (
        db["signals"]
        .find({"work_item_id": work_item_id})
        .sort("timestamp", -1)
        .skip(offset)
        .limit(limit)
    )
    signals = []
    async for doc in cursor:
        doc["signal_id"] = doc.pop("_id", None)
        signals.append(doc)

    total = await db["signals"].count_documents({"work_item_id": work_item_id})

    return {
        "signals": signals,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/{work_item_id}/transition")
async def transition_work_item(work_item_id: str, transition: WorkItemTransition):
    """
    Transition a work item's state.
    Validates against the State Pattern:
    - OPEN → INVESTIGATING
    - INVESTIGATING → RESOLVED
    - RESOLVED → CLOSED (requires RCA)
    - RESOLVED → INVESTIGATING (reopen)
    """
    # Get current state
    row = await pg.fetchrow_with_retry(
        "SELECT state FROM work_items WHERE id = $1", work_item_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Work item not found")

    current_state = WorkItemState(row["state"])

    try:
        result = await state_machine.transition(
            work_item_id=work_item_id,
            current_state=current_state,
            target_state=transition.target_state,
            notes=transition.notes,
            assigned_to=transition.assigned_to,
        )
        return {
            "status": "transitioned",
            "work_item": _row_to_dict_from_dict(result),
        }
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RCARequiredError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{work_item_id}/transitions")
async def get_state_transitions(work_item_id: str):
    """Get the state transition history for a work item."""
    rows = await pg.fetch_with_retry(
        """SELECT * FROM state_transitions
           WHERE work_item_id = $1
           ORDER BY transitioned_at ASC""",
        work_item_id,
    )
    return {"transitions": [_row_to_dict(r) for r in rows]}


def _row_to_dict_from_dict(d: dict) -> dict:
    """Convert a dict with datetime values to JSON-serializable."""
    result = {}
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result

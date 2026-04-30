"""
Work Item State Machine — State Pattern implementation.

Manages transitions:
    OPEN → INVESTIGATING → RESOLVED → CLOSED

The CLOSED transition enforces mandatory RCA validation.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.db import postgres as pg
from app.db import redis_client
from app.models.workitem import WorkItemState, StateTransitionRecord

logger = logging.getLogger(__name__)


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class RCARequiredError(Exception):
    """Raised when trying to close without RCA."""
    pass


# ── State Handlers (State Pattern) ──────────────────────────────────────

class StateHandler(ABC):
    """Abstract base for state-specific transition logic."""

    @abstractmethod
    def get_valid_transitions(self) -> list[WorkItemState]:
        """Return list of valid target states from this state."""
        ...

    @abstractmethod
    async def on_enter(self, work_item_id: str, **kwargs):
        """Logic executed when entering this state."""
        ...


class OpenStateHandler(StateHandler):
    """OPEN state — incident just created, awaiting triage."""

    def get_valid_transitions(self) -> list[WorkItemState]:
        return [WorkItemState.INVESTIGATING]

    async def on_enter(self, work_item_id: str, **kwargs):
        logger.info(f"Work item {work_item_id} entered OPEN state")


class InvestigatingStateHandler(StateHandler):
    """INVESTIGATING state — responder is actively working on the incident."""

    def get_valid_transitions(self) -> list[WorkItemState]:
        return [WorkItemState.RESOLVED]

    async def on_enter(self, work_item_id: str, **kwargs):
        assigned_to = kwargs.get("assigned_to")
        if assigned_to:
            await pg.execute_with_retry(
                "UPDATE work_items SET assigned_to = $1, updated_at = NOW() WHERE id = $2",
                assigned_to, work_item_id,
            )
        logger.info(f"Work item {work_item_id} under investigation by {assigned_to}")


class ResolvedStateHandler(StateHandler):
    """RESOLVED state — fix applied, awaiting RCA for closure."""

    def get_valid_transitions(self) -> list[WorkItemState]:
        return [WorkItemState.CLOSED, WorkItemState.INVESTIGATING]  # Can reopen

    async def on_enter(self, work_item_id: str, **kwargs):
        logger.info(f"Work item {work_item_id} resolved — awaiting RCA for closure")


class ClosedStateHandler(StateHandler):
    """CLOSED state — terminal state, requires completed RCA."""

    def get_valid_transitions(self) -> list[WorkItemState]:
        return []  # Terminal state

    async def on_enter(self, work_item_id: str, **kwargs):
        logger.info(f"Work item {work_item_id} CLOSED with RCA")


# ── State Machine ───────────────────────────────────────────────────────

class WorkItemStateMachine:
    """
    State machine that orchestrates work item lifecycle transitions.
    Uses the State Pattern — each state has its own handler with
    defined valid transitions and entry actions.
    """

    def __init__(self):
        self._handlers: dict[WorkItemState, StateHandler] = {
            WorkItemState.OPEN: OpenStateHandler(),
            WorkItemState.INVESTIGATING: InvestigatingStateHandler(),
            WorkItemState.RESOLVED: ResolvedStateHandler(),
            WorkItemState.CLOSED: ClosedStateHandler(),
        }

    async def transition(
        self,
        work_item_id: str,
        current_state: WorkItemState,
        target_state: WorkItemState,
        notes: str = None,
        assigned_to: str = None,
    ) -> dict:
        """
        Attempt a state transition.

        Validates:
        1. Target state is reachable from current state
        2. CLOSED requires a completed RCA

        Returns updated work item data.
        """
        current_handler = self._handlers[current_state]

        # Validate transition
        valid_targets = current_handler.get_valid_transitions()
        if target_state not in valid_targets:
            raise InvalidTransitionError(
                f"Cannot transition from {current_state.value} to {target_state.value}. "
                f"Valid transitions: {[s.value for s in valid_targets]}"
            )

        # CLOSED requires RCA
        if target_state == WorkItemState.CLOSED:
            rca = await pg.fetchrow_with_retry(
                "SELECT id FROM rca_records WHERE work_item_id = $1",
                work_item_id,
            )
            if not rca:
                raise RCARequiredError(
                    f"Cannot close work item {work_item_id}: RCA is required. "
                    "Please submit a complete Root Cause Analysis before closing."
                )

        # Execute transition atomically
        pool = await pg.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Update work item state
                now = datetime.now(timezone.utc)
                row = await conn.fetchrow(
                    """UPDATE work_items
                       SET state = $1, updated_at = $2
                       WHERE id = $3
                       RETURNING *""",
                    target_state.value, now, work_item_id,
                )

                # Record state transition
                record = StateTransitionRecord(
                    work_item_id=work_item_id,
                    from_state=current_state,
                    to_state=target_state,
                    notes=notes,
                )
                await conn.execute(
                    """INSERT INTO state_transitions
                       (id, work_item_id, from_state, to_state, transitioned_at, notes)
                       VALUES ($1, $2, $3, $4, $5, $6)""",
                    record.id, work_item_id,
                    current_state.value, target_state.value,
                    record.transitioned_at, notes,
                )

                # If closing, update MTTR from RCA
                if target_state == WorkItemState.CLOSED:
                    rca_row = await conn.fetchrow(
                        "SELECT mttr_seconds FROM rca_records WHERE work_item_id = $1",
                        work_item_id,
                    )
                    if rca_row:
                        await conn.execute(
                            "UPDATE work_items SET mttr_seconds = $1 WHERE id = $2",
                            rca_row["mttr_seconds"], work_item_id,
                        )

        # Run on_enter actions for the new state
        target_handler = self._handlers[target_state]
        await target_handler.on_enter(work_item_id, assigned_to=assigned_to)

        # Invalidate cache
        await redis_client.invalidate_work_item_cache(work_item_id)

        # Publish real-time event
        await redis_client.publish_event("incidents", {
            "type": "state_changed",
            "work_item_id": work_item_id,
            "from_state": current_state.value,
            "to_state": target_state.value,
        })

        # Return updated data
        updated = await pg.fetchrow_with_retry(
            "SELECT * FROM work_items WHERE id = $1", work_item_id
        )
        return dict(updated) if updated else {}


# Singleton
state_machine = WorkItemStateMachine()

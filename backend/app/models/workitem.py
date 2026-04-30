"""
WorkItem model — represents a deduplicated incident created from debounced signals.
Stored in PostgreSQL as the Source of Truth.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkItemState(str, Enum):
    """Work item lifecycle states."""
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class WorkItem(BaseModel):
    """Structured work item stored in PostgreSQL."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    component_id: str
    component_type: str
    severity: str
    state: WorkItemState = WorkItemState.OPEN
    signal_count: int = 1
    title: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_to: Optional[str] = None
    mttr_seconds: Optional[float] = None
    first_signal_time: Optional[datetime] = None

    def generate_title(self) -> str:
        """Auto-generate a descriptive title."""
        return f"[{self.severity}] {self.component_type} failure on {self.component_id}"


class WorkItemTransition(BaseModel):
    """Request to transition a work item's state."""
    target_state: WorkItemState
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class StateTransitionRecord(BaseModel):
    """Audit record of a state transition."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    work_item_id: str
    from_state: WorkItemState
    to_state: WorkItemState
    transitioned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None

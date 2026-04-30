"""
Signal model — represents a raw error/latency signal from infrastructure.
Stored in MongoDB as the audit log (Data Lake).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ComponentType(str, Enum):
    """Types of infrastructure components being monitored."""
    API = "API"
    MCP = "MCP"
    CACHE = "CACHE"
    QUEUE = "QUEUE"
    RDBMS = "RDBMS"
    NOSQL = "NOSQL"


class Severity(str, Enum):
    """Incident severity levels (P0 = most critical)."""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


# Maps component types to their default severity
COMPONENT_SEVERITY_MAP: dict[str, Severity] = {
    ComponentType.RDBMS: Severity.P0,
    ComponentType.QUEUE: Severity.P1,
    ComponentType.MCP: Severity.P1,
    ComponentType.NOSQL: Severity.P1,
    ComponentType.CACHE: Severity.P2,
    ComponentType.API: Severity.P2,
}


class SignalIn(BaseModel):
    """Inbound signal payload from producers."""
    component_id: str  # e.g., CACHE_CLUSTER_01
    component_type: ComponentType
    severity: Optional[Severity] = None  # auto-derived from component_type if missing
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class Signal(BaseModel):
    """Full signal record stored in MongoDB."""
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    component_id: str
    component_type: ComponentType
    severity: Severity
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    work_item_id: Optional[str] = None  # linked after debounce

    @classmethod
    def from_input(cls, signal_in: SignalIn) -> "Signal":
        """Create a Signal from inbound payload, auto-deriving severity if needed."""
        severity = signal_in.severity or COMPONENT_SEVERITY_MAP.get(
            signal_in.component_type, Severity.P3
        )
        return cls(
            component_id=signal_in.component_id,
            component_type=signal_in.component_type,
            severity=severity,
            message=signal_in.message,
            payload=signal_in.payload,
            timestamp=signal_in.timestamp or datetime.now(timezone.utc),
        )

    def to_mongo(self) -> dict:
        """Convert to MongoDB-friendly dict."""
        d = self.model_dump()
        d["_id"] = d.pop("signal_id")
        d["timestamp"] = d["timestamp"].isoformat()
        return d

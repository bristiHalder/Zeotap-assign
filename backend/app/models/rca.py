"""
RCA (Root Cause Analysis) model with strict validation.
System rejects CLOSED transition if RCA is missing or incomplete.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class RootCauseCategory(str, Enum):
    """Standard root cause categories."""
    INFRASTRUCTURE = "Infrastructure"
    CODE_BUG = "Code Bug"
    CONFIGURATION = "Configuration"
    EXTERNAL_DEPENDENCY = "External Dependency"
    CAPACITY = "Capacity"
    HUMAN_ERROR = "Human Error"
    NETWORK = "Network"
    SECURITY = "Security"
    UNKNOWN = "Unknown"


class RCACreate(BaseModel):
    """Inbound RCA submission."""
    incident_start: datetime
    incident_end: datetime
    root_cause_category: RootCauseCategory
    root_cause_description: str
    fix_applied: str
    prevention_steps: str

    @model_validator(mode="after")
    def validate_completeness(self):
        """Reject incomplete RCA submissions."""
        errors = []
        if not self.root_cause_description or self.root_cause_description.strip() == "":
            errors.append("root_cause_description is required")
        if not self.fix_applied or self.fix_applied.strip() == "":
            errors.append("fix_applied is required")
        if not self.prevention_steps or self.prevention_steps.strip() == "":
            errors.append("prevention_steps is required")
        if self.incident_end <= self.incident_start:
            errors.append("incident_end must be after incident_start")
        if errors:
            raise ValueError(f"Incomplete RCA: {'; '.join(errors)}")
        return self


class RCA(BaseModel):
    """Full RCA record stored in PostgreSQL."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    work_item_id: str
    incident_start: datetime
    incident_end: datetime
    root_cause_category: RootCauseCategory
    root_cause_description: str
    fix_applied: str
    prevention_steps: str
    mttr_seconds: float = 0.0
    created_at: Optional[datetime] = None

    @classmethod
    def from_create(cls, work_item_id: str, rca_in: RCACreate) -> "RCA":
        """Create RCA and calculate MTTR."""
        mttr = (rca_in.incident_end - rca_in.incident_start).total_seconds()
        return cls(
            work_item_id=work_item_id,
            incident_start=rca_in.incident_start,
            incident_end=rca_in.incident_end,
            root_cause_category=rca_in.root_cause_category,
            root_cause_description=rca_in.root_cause_description,
            fix_applied=rca_in.fix_applied,
            prevention_steps=rca_in.prevention_steps,
            mttr_seconds=mttr,
        )

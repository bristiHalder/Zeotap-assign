"""
Unit tests for RCA validation logic.
Tests that incomplete RCAs are rejected and MTTR is calculated correctly.
"""

import pytest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError

from app.models.rca import RCA, RCACreate, RootCauseCategory


class TestRCAValidation:
    """Test suite for RCA completeness validation."""

    def _valid_rca_data(self) -> dict:
        """Helper: returns valid RCA data."""
        now = datetime.now(timezone.utc)
        return {
            "incident_start": now - timedelta(hours=2),
            "incident_end": now,
            "root_cause_category": RootCauseCategory.INFRASTRUCTURE,
            "root_cause_description": "Database connection pool exhausted due to connection leak",
            "fix_applied": "Patched connection pool to properly release connections on timeout",
            "prevention_steps": "Added connection pool monitoring alerts and implemented connection timeout",
        }

    def test_valid_rca_accepted(self):
        """Test that a complete RCA passes validation."""
        data = self._valid_rca_data()
        rca = RCACreate(**data)
        assert rca.root_cause_category == RootCauseCategory.INFRASTRUCTURE
        assert rca.fix_applied != ""

    def test_empty_root_cause_description_rejected(self):
        """Test that empty root_cause_description is rejected."""
        data = self._valid_rca_data()
        data["root_cause_description"] = ""
        with pytest.raises(ValidationError) as exc_info:
            RCACreate(**data)
        assert "root_cause_description is required" in str(exc_info.value)

    def test_whitespace_only_fix_applied_rejected(self):
        """Test that whitespace-only fix_applied is rejected."""
        data = self._valid_rca_data()
        data["fix_applied"] = "   "
        with pytest.raises(ValidationError) as exc_info:
            RCACreate(**data)
        assert "fix_applied is required" in str(exc_info.value)

    def test_empty_prevention_steps_rejected(self):
        """Test that empty prevention_steps is rejected."""
        data = self._valid_rca_data()
        data["prevention_steps"] = ""
        with pytest.raises(ValidationError) as exc_info:
            RCACreate(**data)
        assert "prevention_steps is required" in str(exc_info.value)

    def test_end_before_start_rejected(self):
        """Test that incident_end before incident_start is rejected."""
        data = self._valid_rca_data()
        data["incident_end"] = data["incident_start"] - timedelta(hours=1)
        with pytest.raises(ValidationError) as exc_info:
            RCACreate(**data)
        assert "incident_end must be after incident_start" in str(exc_info.value)

    def test_multiple_missing_fields_all_reported(self):
        """Test that all validation errors are reported together."""
        data = self._valid_rca_data()
        data["root_cause_description"] = ""
        data["fix_applied"] = ""
        data["prevention_steps"] = ""
        with pytest.raises(ValidationError) as exc_info:
            RCACreate(**data)
        error_str = str(exc_info.value)
        assert "root_cause_description" in error_str
        assert "fix_applied" in error_str
        assert "prevention_steps" in error_str

    def test_mttr_calculation(self):
        """Test that MTTR is correctly calculated from start/end times."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=2, minutes=30)
        end = now

        data = self._valid_rca_data()
        data["incident_start"] = start
        data["incident_end"] = end

        rca_in = RCACreate(**data)
        rca = RCA.from_create("test-work-item-id", rca_in)

        expected_mttr = 2 * 3600 + 30 * 60  # 9000 seconds
        assert rca.mttr_seconds == expected_mttr
        assert rca.work_item_id == "test-work-item-id"

    def test_mttr_short_incident(self):
        """Test MTTR for a short incident (5 minutes)."""
        now = datetime.now(timezone.utc)
        data = self._valid_rca_data()
        data["incident_start"] = now - timedelta(minutes=5)
        data["incident_end"] = now

        rca_in = RCACreate(**data)
        rca = RCA.from_create("short-incident", rca_in)

        assert rca.mttr_seconds == 300  # 5 minutes in seconds

    def test_all_root_cause_categories_valid(self):
        """Test that all root cause categories are accepted."""
        for category in RootCauseCategory:
            data = self._valid_rca_data()
            data["root_cause_category"] = category
            rca = RCACreate(**data)
            assert rca.root_cause_category == category

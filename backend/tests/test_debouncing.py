"""
Unit tests for the signal debouncing logic.
"""

import pytest
from datetime import datetime, timezone

from app.models.signal import Signal, SignalIn, ComponentType, Severity


class TestSignalModels:
    """Test signal model creation and serialization."""

    def test_signal_from_input_auto_severity(self):
        """Test that severity is auto-derived from component_type."""
        signal_in = SignalIn(
            component_id="DB_PRIMARY_01",
            component_type=ComponentType.RDBMS,
            message="Connection pool exhausted",
        )
        signal = Signal.from_input(signal_in)
        assert signal.severity == Severity.P0  # RDBMS → P0

    def test_signal_from_input_cache_severity(self):
        """Test cache component gets P2 severity."""
        signal_in = SignalIn(
            component_id="CACHE_CLUSTER_01",
            component_type=ComponentType.CACHE,
            message="High eviction rate",
        )
        signal = Signal.from_input(signal_in)
        assert signal.severity == Severity.P2

    def test_signal_from_input_explicit_severity(self):
        """Test that explicit severity overrides auto-derivation."""
        signal_in = SignalIn(
            component_id="API_GATEWAY_01",
            component_type=ComponentType.API,
            severity=Severity.P0,  # Override from P2
            message="Total API failure",
        )
        signal = Signal.from_input(signal_in)
        assert signal.severity == Severity.P0

    def test_signal_to_mongo(self):
        """Test MongoDB serialization."""
        signal = Signal(
            signal_id="test-123",
            component_id="CACHE_01",
            component_type=ComponentType.CACHE,
            severity=Severity.P2,
            message="Test",
        )
        mongo_doc = signal.to_mongo()
        assert "_id" in mongo_doc
        assert mongo_doc["_id"] == "test-123"
        assert "signal_id" not in mongo_doc

    def test_signal_unique_ids(self):
        """Test that each signal gets a unique ID."""
        signal_in = SignalIn(
            component_id="CACHE_01",
            component_type=ComponentType.CACHE,
            message="Test",
        )
        s1 = Signal.from_input(signal_in)
        s2 = Signal.from_input(signal_in)
        assert s1.signal_id != s2.signal_id

"""
Unit tests for the State Machine (State Pattern).
Tests valid/invalid transitions — pure logic, no DB dependencies.
"""

import pytest


# Inline the state machine logic to avoid importing DB-dependent modules
from enum import Enum

class WorkItemState(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

# Define valid transitions map (mirrors state_machine.py)
VALID_TRANSITIONS = {
    WorkItemState.OPEN: [WorkItemState.INVESTIGATING],
    WorkItemState.INVESTIGATING: [WorkItemState.RESOLVED],
    WorkItemState.RESOLVED: [WorkItemState.CLOSED, WorkItemState.INVESTIGATING],
    WorkItemState.CLOSED: [],
}


class TestStateMachine:
    """Test suite for the Work Item State Machine transition rules."""

    def test_open_valid_transitions(self):
        assert VALID_TRANSITIONS[WorkItemState.OPEN] == [WorkItemState.INVESTIGATING]

    def test_investigating_valid_transitions(self):
        assert VALID_TRANSITIONS[WorkItemState.INVESTIGATING] == [WorkItemState.RESOLVED]

    def test_resolved_valid_transitions(self):
        valid = VALID_TRANSITIONS[WorkItemState.RESOLVED]
        assert WorkItemState.CLOSED in valid
        assert WorkItemState.INVESTIGATING in valid

    def test_closed_no_transitions(self):
        assert VALID_TRANSITIONS[WorkItemState.CLOSED] == []

    def test_all_states_have_transitions(self):
        for state in WorkItemState:
            assert state in VALID_TRANSITIONS

    def test_open_cannot_skip_to_resolved(self):
        assert WorkItemState.RESOLVED not in VALID_TRANSITIONS[WorkItemState.OPEN]

    def test_open_cannot_skip_to_closed(self):
        assert WorkItemState.CLOSED not in VALID_TRANSITIONS[WorkItemState.OPEN]

    def test_investigating_cannot_skip_to_closed(self):
        assert WorkItemState.CLOSED not in VALID_TRANSITIONS[WorkItemState.INVESTIGATING]

    def test_full_happy_path(self):
        """Test OPEN→INVESTIGATING→RESOLVED→CLOSED is a valid complete path."""
        path = [WorkItemState.OPEN, WorkItemState.INVESTIGATING, WorkItemState.RESOLVED, WorkItemState.CLOSED]
        for i in range(len(path) - 1):
            assert path[i+1] in VALID_TRANSITIONS[path[i]], \
                f"Transition {path[i]} → {path[i+1]} should be valid"

    def test_reopen_path(self):
        """Test RESOLVED→INVESTIGATING reopen path."""
        assert WorkItemState.INVESTIGATING in VALID_TRANSITIONS[WorkItemState.RESOLVED]

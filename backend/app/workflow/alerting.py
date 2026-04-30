"""
Alerting Engine — Strategy Pattern implementation.

Different component failures require different alert types:
- P0 (RDBMS failure) → Critical: PagerDuty-style immediate alert
- P1 (Queue/MCP/NoSQL failure) → High: Slack urgent channel
- P2 (Cache/API failure) → Medium: Email notification
- P3 (Other) → Low: Dashboard notification only

In production, these would integrate with real alerting services.
For this demo, they log to console with appropriate formatting.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.models.signal import Signal, Severity

logger = logging.getLogger(__name__)


# ── Alert Strategy Interface (Strategy Pattern) ─────────────────────────

class AlertStrategy(ABC):
    """Abstract strategy for sending alerts."""

    @abstractmethod
    async def send_alert(self, signal: Signal, work_item_id: str = None) -> dict:
        """
        Send an alert for the given signal.
        Returns alert metadata (channel, status, etc.)
        """
        ...

    @abstractmethod
    def get_priority_label(self) -> str:
        """Human-readable priority label."""
        ...


class CriticalAlertStrategy(AlertStrategy):
    """
    P0 — Critical Alert (RDBMS failures)
    In production: PagerDuty page, phone call, SMS
    Demo: console log with CRITICAL formatting
    """

    async def send_alert(self, signal: Signal, work_item_id: str = None) -> dict:
        alert_msg = (
            f"CRITICAL ALERT [P0]\n"
            f"  Component: {signal.component_id} ({signal.component_type.value})\n"
            f"  Message: {signal.message}\n"
            f"  Work Item: {work_item_id}\n"
            f"  Time: {datetime.now(timezone.utc).isoformat()}\n"
            f"  Action: IMMEDIATE RESPONSE REQUIRED -- PagerDuty alert triggered"
        )
        logger.critical(alert_msg)
        return {
            "channel": "pagerduty",
            "priority": "P0",
            "status": "sent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_priority_label(self) -> str:
        return "P0 - Critical (PagerDuty)"


class HighAlertStrategy(AlertStrategy):
    """
    P1 — High Priority Alert (Queue/MCP/NoSQL failures)
    In production: Slack urgent channel, on-call notification
    Demo: console log with WARNING formatting
    """

    async def send_alert(self, signal: Signal, work_item_id: str = None) -> dict:
        alert_msg = (
            f"HIGH PRIORITY ALERT [P1]\n"
            f"  Component: {signal.component_id} ({signal.component_type.value})\n"
            f"  Message: {signal.message}\n"
            f"  Work Item: {work_item_id}\n"
            f"  Time: {datetime.now(timezone.utc).isoformat()}\n"
            f"  Action: Slack #incidents-urgent notification sent"
        )
        logger.warning(alert_msg)
        return {
            "channel": "slack-urgent",
            "priority": "P1",
            "status": "sent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_priority_label(self) -> str:
        return "P1 - High (Slack Urgent)"


class MediumAlertStrategy(AlertStrategy):
    """
    P2 — Medium Priority Alert (Cache/API failures)
    In production: Email to engineering team, Slack general
    Demo: console log with INFO formatting
    """

    async def send_alert(self, signal: Signal, work_item_id: str = None) -> dict:
        alert_msg = (
            f"MEDIUM ALERT [P2]\n"
            f"  Component: {signal.component_id} ({signal.component_type.value})\n"
            f"  Message: {signal.message}\n"
            f"  Work Item: {work_item_id}\n"
            f"  Time: {datetime.now(timezone.utc).isoformat()}\n"
            f"  Action: Email notification sent to engineering team"
        )
        logger.info(alert_msg)
        return {
            "channel": "email",
            "priority": "P2",
            "status": "sent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_priority_label(self) -> str:
        return "P2 - Medium (Email)"


class LowAlertStrategy(AlertStrategy):
    """
    P3 — Low Priority Alert (minor issues)
    Dashboard notification only, no external alerting.
    """

    async def send_alert(self, signal: Signal, work_item_id: str = None) -> dict:
        alert_msg = (
            f"LOW ALERT [P3]\n"
            f"  Component: {signal.component_id} ({signal.component_type.value})\n"
            f"  Message: {signal.message}\n"
            f"  Action: Dashboard notification only"
        )
        logger.info(alert_msg)
        return {
            "channel": "dashboard",
            "priority": "P3",
            "status": "logged",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_priority_label(self) -> str:
        return "P3 - Low (Dashboard)"


# ── Alert Engine ────────────────────────────────────────────────────────

class AlertEngine:
    """
    Alert engine that uses the Strategy Pattern to dispatch alerts
    based on signal severity. Strategies are swappable at runtime.
    """

    def __init__(self):
        self._strategies: dict[str, AlertStrategy] = {
            Severity.P0: CriticalAlertStrategy(),
            Severity.P1: HighAlertStrategy(),
            Severity.P2: MediumAlertStrategy(),
            Severity.P3: LowAlertStrategy(),
        }

    def register_strategy(self, severity: Severity, strategy: AlertStrategy):
        """Register or replace an alert strategy for a severity level."""
        self._strategies[severity] = strategy
        logger.info(f"Registered alert strategy for {severity}: {strategy.get_priority_label()}")

    def get_strategy(self, severity: Severity) -> AlertStrategy:
        """Get the alert strategy for a given severity."""
        return self._strategies.get(severity, self._strategies[Severity.P3])

    async def trigger_alert(self, signal: Signal, work_item_id: str = None) -> dict:
        """Trigger the appropriate alert based on signal severity."""
        strategy = self.get_strategy(signal.severity)
        return await strategy.send_alert(signal, work_item_id)


# Singleton
alert_engine = AlertEngine()

# Design Patterns

## 1. Strategy Pattern — Alerting Engine

### Problem
Different infrastructure component failures require different alert channels and urgency levels. RDBMS failures need immediate paging, while cache misses can wait for an email.

### Solution
The **Strategy Pattern** encapsulates each alerting behavior behind a common interface:

```python
class AlertStrategy(ABC):
    @abstractmethod
    async def send_alert(self, signal, work_item_id) -> dict: ...

class CriticalAlertStrategy(AlertStrategy):  # P0 → PagerDuty
class HighAlertStrategy(AlertStrategy):       # P1 → Slack Urgent
class MediumAlertStrategy(AlertStrategy):     # P2 → Email
class LowAlertStrategy(AlertStrategy):        # P3 → Dashboard only
```

The `AlertEngine` selects the strategy based on signal severity:
```python
class AlertEngine:
    def __init__(self):
        self._strategies = {
            Severity.P0: CriticalAlertStrategy(),
            Severity.P1: HighAlertStrategy(),
            ...
        }

    async def trigger_alert(self, signal):
        strategy = self._strategies[signal.severity]
        return await strategy.send_alert(signal)
```

### Benefits
- **Open/Closed Principle**: Add new alert types without modifying existing code
- **Runtime swappable**: `engine.register_strategy(Severity.P0, SlackStrategy())` replaces PagerDuty with Slack at runtime
- **Testable**: Each strategy can be unit-tested independently

---

## 2. State Pattern — Work Item Lifecycle

### Problem
Work items must follow a strict lifecycle (OPEN → INVESTIGATING → RESOLVED → CLOSED) with different rules at each state (e.g., CLOSED requires RCA).

### Solution
Each state is a separate handler class:

```python
class StateHandler(ABC):
    @abstractmethod
    def get_valid_transitions(self) -> list[WorkItemState]: ...
    @abstractmethod
    async def on_enter(self, work_item_id, **kwargs): ...

class OpenStateHandler(StateHandler):
    def get_valid_transitions(self): return [INVESTIGATING]

class ResolvedStateHandler(StateHandler):
    def get_valid_transitions(self): return [CLOSED, INVESTIGATING]
```

The `WorkItemStateMachine` orchestrates transitions:
1. Validate target state is reachable from current state
2. If target is CLOSED → verify RCA exists (reject with error if not)
3. Execute transition atomically (PostgreSQL transaction)
4. Record audit trail in `state_transitions` table
5. Run `on_enter` actions for new state

### Benefits
- **Type safety**: Invalid transitions are impossible
- **Mandatory RCA enforcement**: Built into the CLOSED state's entry guard
- **Audit trail**: Every transition is recorded with timestamp and notes
- **Reopenable**: RESOLVED → INVESTIGATING allows reopening if fix fails

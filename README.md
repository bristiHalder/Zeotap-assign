# 🛡️ Mission-Critical Incident Management System (IMS)

A production-grade Incident Management System designed to monitor complex distributed infrastructure (APIs, MCP Hosts, Distributed Caches, Async Queues, RDBMS, and NoSQL stores) and manage failure mediation workflows.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SIGNAL PRODUCERS                             │
│   (APIs, MCP Hosts, Caches, Queues, RDBMS, NoSQL)                  │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ POST /api/v1/signals (JSON)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     INGESTION LAYER (FastAPI)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐    │
│  │ Rate Limiter  │→│ Async Queue  │→│  Debounce Processor     │    │
│  │(Token Bucket) │  │(asyncio.Q)   │  │(Redis sliding window)  │    │
│  │ 5000 req/s    │  │ max=50,000   │  │ 100 signals/10s = 1 WI│    │
│  └──────────────┘  └──────────────┘  └───────┬────────────────┘    │
└───────────────────────────────────────────────┼─────────────────────┘
                    ┌───────────────────────────┼──────────────────┐
                    ▼                           ▼                  ▼
        ┌───────────────────┐     ┌──────────────────┐   ┌────────────────┐
        │   MongoDB (Lake)  │     │ PostgreSQL (SoT)  │   │  Redis (Cache) │
        │   Raw Signals     │     │  Work Items + RCA │   │  Dashboard     │
        │   Audit Log       │     │  ACID Transactions│   │  State + TS    │
        └───────────────────┘     └──────────────────┘   └────────────────┘
                                          │ WebSocket
                                          ▼
                                ┌──────────────────┐
                                │  React Dashboard  │
                                │  Live Feed | RCA  │
                                └──────────────────┘
```

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | Python 3.12 + FastAPI | Async API, high throughput |
| RDBMS | PostgreSQL 16 | Source of Truth (Work Items, RCA) — ACID |
| NoSQL | MongoDB 7 | Data Lake (Raw Signals) — Audit Log |
| Cache | Redis 7 | Hot-path dashboard, debouncing, pub/sub |
| Frontend | React + Vite | Real-time incident dashboard |
| Infra | Docker Compose | Single-command deployment |

## Quick Start

### Prerequisites
- Docker & Docker Compose

### Launch

```bash
# Clone and start
git clone https://github.com/bristiHalder/Zeotap-Assignment.git
cd Zeotap-Assignment
docker compose up --build
```

**Access:**
- 🌐 Dashboard: http://localhost:3000
- 📡 API Docs: http://localhost:8000/docs
- ❤️ Health: http://localhost:8000/health

### Run Failure Simulation

```bash
# Install httpx for async requests (optional, falls back to urllib)
pip install httpx

# Send 10,000 cascading failure signals
python scripts/simulate_failure.py --signals 10000
```

## How Backpressure Is Handled

The system uses a **3-layer defense** against signal floods:

### Layer 1: Rate Limiting (Token Bucket)
- Incoming signals pass through a token-bucket rate limiter (5000 req/s default)
- When tokens are exhausted → `429 Too Many Requests`
- Burst tolerance: 2× the rate limit

### Layer 2: Bounded Async Queue
- Accepted signals are placed in a bounded `asyncio.Queue` (capacity: 50,000)
- Non-blocking enqueue: if queue is full → `503 Service Unavailable`
- Producers receive immediate feedback to back off
- **Key insight:** The API handler returns `202 Accepted` before processing — the queue decouples ingestion speed from persistence speed

### Layer 3: Worker Pool
- 4 concurrent worker coroutines drain the queue
- Each worker processes signals through: MongoDB write → debounce check → work item creation
- Workers have independent retry loops with exponential backoff for DB writes
- If MongoDB/PostgreSQL is slow, the queue absorbs the burst; if it exceeds 50K, backpressure propagates upstream via 503

## Design Patterns

### Strategy Pattern — Alerting Engine
Different component failures trigger different alert channels:
- **P0 (RDBMS):** Critical — PagerDuty-style immediate alert
- **P1 (Queue/MCP):** High — Slack urgent channel
- **P2 (Cache/API):** Medium — Email notification
- **P3:** Low — Dashboard only

Strategies are swappable at runtime via `AlertEngine.register_strategy()`.

### State Pattern — Work Item Lifecycle
```
OPEN → INVESTIGATING → RESOLVED → CLOSED
                          ↑           │
                          └───────────┘ (reopen)
```
- Each state has its own handler with defined valid transitions
- **CLOSED requires mandatory RCA** — rejected with 422 if missing
- Transitions are recorded in an audit table

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/signals/` | Ingest single signal |
| POST | `/api/v1/signals/batch` | Batch ingest (≤1000) |
| GET | `/api/v1/workitems/` | List work items (filterable) |
| GET | `/api/v1/workitems/{id}` | Get work item detail |
| GET | `/api/v1/workitems/{id}/signals` | Get linked raw signals |
| PATCH | `/api/v1/workitems/{id}/transition` | Transition state |
| POST | `/api/v1/workitems/{id}/rca` | Submit RCA |
| GET | `/api/v1/workitems/{id}/rca` | Get RCA |
| GET | `/api/v1/dashboard/stats` | Dashboard statistics |
| GET | `/health` | Health + metrics |
| WS | `/api/v1/ws` | Real-time WebSocket |

## Observability

- **Health endpoint** (`/health`): DB connectivity, queue depth, throughput
- **Console metrics**: Prints signals/sec every 5 seconds
- **WebSocket**: Real-time push for new incidents and state changes

## Testing

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/ -v
```

Tests cover:
- RCA validation (completeness, MTTR calculation)
- State machine transitions (valid/invalid paths)
- Signal model creation and serialization

## Non-Functional Features

- **Rate Limiting:** Token-bucket prevents cascading failures
- **Retry Logic:** Exponential backoff for PostgreSQL and MongoDB writes
- **Connection Pooling:** asyncpg (5-20 connections), Motor (50 connections)
- **Concurrency:** asyncio for non-blocking I/O, bounded queue for memory safety
- **Caching:** Redis hot-path for dashboard stats (10s TTL), work item cache (60s TTL)

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings (env vars)
│   │   ├── models/              # Pydantic models
│   │   ├── ingestion/           # Rate limiter, queue, debouncer
│   │   ├── workflow/            # State machine, alerting engine
│   │   ├── routes/              # API endpoints
│   │   ├── services/            # Metrics service
│   │   └── db/                  # Database clients
│   ├── tests/                   # Unit tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/               # Dashboard, IncidentDetail, RCAForm
│   │   ├── hooks/               # useWebSocket
│   │   └── services/            # API client
│   ├── Dockerfile
│   └── nginx.conf
├── scripts/
│   ├── simulate_failure.py      # Failure simulation (10K+ signals)
│   └── sample_signals.json      # Sample payloads
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DESIGN_PATTERNS.md
│   └── BACKPRESSURE.md
└── docker-compose.yml
```

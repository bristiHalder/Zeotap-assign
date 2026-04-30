# Architecture Documentation

## System Overview

The IMS follows an **event-driven architecture** with clear separation of concerns across three data stores, each chosen for its specific strengths.

## Data Flow

```
Signal Producer → Rate Limiter → Async Queue → Processor → Storage
                     │                              │
                  429 if over                ┌──────┼──────┐
                  rate limit                 │      │      │
                                          MongoDB  PG   Redis
                                          (lake) (SoT) (cache)
```

### 1. Ingestion Layer
- **Rate Limiter**: Token-bucket algorithm running in-process. Each token represents permission to process one signal. Tokens refill at a configurable rate (default 5000/sec). Burst capacity is 2× the rate.
- **Backpressure Queue**: `asyncio.Queue(maxsize=50000)` — bounded to prevent OOM. Non-blocking `put_nowait()` returns immediately. If full, the API returns `503`.
- **Worker Pool**: N coroutines (default 4) that drain the queue. Each worker independently processes signals and has its own retry loop.

### 2. Debouncing
- Uses **Redis Sorted Sets** keyed by `debounce:{component_id}`
- Each signal is added with its timestamp as score
- On each insert, expired entries (outside 10s window) are pruned
- When count ≥ 100 → create ONE work item, link all signals
- First signal for a new component always creates a work item immediately

### 3. Storage Strategy

| Store | Data | Access Pattern | Why |
|-------|------|---------------|-----|
| MongoDB | Raw signals | Write-heavy, schema-flexible | High throughput inserts, rich querying for audit |
| PostgreSQL | Work items, RCA, transitions | Read/write, transactional | ACID guarantees for state transitions |
| Redis | Dashboard cache, debounce windows | Read-heavy, ephemeral | Sub-ms latency for UI, sorted sets for debouncing |

### 4. Real-time Updates
- WebSocket endpoint subscribes to Redis Pub/Sub channel `incidents`
- When work items are created/transitioned, events are published
- Connected dashboard clients receive updates instantly

## Concurrency Model
- Single-process, single-threaded async (uvicorn + asyncio)
- All I/O is non-blocking (asyncpg, motor, aioredis)
- No thread locks needed — asyncio event loop handles scheduling
- Queue provides natural producer/consumer coordination

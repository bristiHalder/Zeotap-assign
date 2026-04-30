# Backpressure Handling

## The Problem
In a production environment, signals arrive in bursts of up to 10,000/sec. If the persistence layer (MongoDB, PostgreSQL) cannot keep up, naive implementations either:
1. **Crash** from OOM (unbounded queues)
2. **Block** the API, causing producer timeouts
3. **Drop silently**, losing audit data

## Our 3-Layer Defense

### Layer 1: Rate Limiting (Ingress Gate)
```
Request → [Token Bucket: 5000 tokens/sec] → Accepted
                     │
                     └→ 429 Too Many Requests (tokens exhausted)
```
- **Algorithm**: Token bucket with configurable rate
- **Burst tolerance**: 2× rate (10,000 tokens max)
- **Effect**: Prevents any single producer from flooding the system

### Layer 2: Bounded Async Queue (Memory Safety)
```
Accepted → [asyncio.Queue(maxsize=50000)] → Workers
                     │
                     └→ 503 Service Unavailable (queue full)
```
- **Non-blocking enqueue**: `put_nowait()` returns immediately
- **Bounded capacity**: 50,000 signals max — prevents OOM
- **Decouples speed**: API returns 202 instantly; processing happens async
- **Observable**: Queue depth exposed in `/health` and console metrics

### Layer 3: Worker Pool (Controlled Drain)
```
Queue → [Worker 1] → MongoDB + PostgreSQL
        [Worker 2] → MongoDB + PostgreSQL
        [Worker 3] → MongoDB + PostgreSQL
        [Worker 4] → MongoDB + PostgreSQL
```
- 4 concurrent workers drain the queue
- Each has independent retry logic (exponential backoff: 100ms → 200ms → 400ms)
- If DBs are slow, queue naturally fills up → Layer 2 activates

## Backpressure Signal Propagation
```
DB slow → Queue fills → 503 to producer → Producer backs off
```

The `503 Service Unavailable` response is the explicit backpressure signal. Well-behaved producers implement:
- Exponential backoff on 503
- Local buffering with retry
- Circuit breaker if 503 rate exceeds threshold

## Metrics & Observability
Every 5 seconds, the system prints:
- `Throughput`: Signals processed per second
- `Queue utilization`: Current/Max with percentage
- `Dropped`: Signals rejected due to full queue
- `Rate Limited`: Signals rejected by rate limiter

This gives operators real-time visibility into backpressure conditions.

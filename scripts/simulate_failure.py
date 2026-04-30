#!/usr/bin/env python3
"""
Failure Simulation Script for IMS.
Simulates a cascading infrastructure failure:
  1. RDBMS outage (P0 burst)
  2. MCP failures from DB dependency (P1)
  3. Cache degradation (P2)
  4. API errors from downstream failures (P2)

Sends 10,000+ signals to demonstrate debouncing, backpressure, and alerting.

Usage:
    python scripts/simulate_failure.py [--url http://localhost:8000] [--signals 10000]
"""

import argparse
import asyncio
import json
import random
import time
from datetime import datetime, timezone

try:
    import httpx
    USE_HTTPX = True
except ImportError:
    import urllib.request
    USE_HTTPX = False

API_URL = "http://localhost:8000"

FAILURE_SCENARIOS = [
    {
        "name": "Phase 1: RDBMS Primary Outage",
        "component_id": "RDBMS_PRIMARY_01",
        "component_type": "RDBMS",
        "messages": [
            "Connection pool exhausted - max connections reached",
            "Query timeout after 30000ms on table: users",
            "Replication lag exceeded 60s threshold",
            "Deadlock detected in transaction T-4521",
            "Disk I/O latency spike: 850ms avg (threshold: 50ms)",
        ],
        "count": 3000,
        "delay": 0.0005,
    },
    {
        "name": "Phase 2: MCP Host Cascade Failure",
        "component_id": "MCP_HOST_ALPHA",
        "component_type": "MCP",
        "messages": [
            "Tool execution timeout: database_query tool unresponsive",
            "Context window overflow - accumulated error responses",
            "Health check failed: downstream RDBMS unreachable",
            "Memory usage critical: 94% of allocated heap",
        ],
        "count": 2500,
        "delay": 0.0008,
    },
    {
        "name": "Phase 3: Cache Cluster Degradation",
        "component_id": "CACHE_CLUSTER_01",
        "component_type": "CACHE",
        "messages": [
            "Cache miss rate exceeded 85% threshold",
            "Eviction rate spike: 12000 keys/sec",
            "Memory fragmentation ratio: 2.3 (threshold: 1.5)",
            "Cluster node redis-node-3 unreachable",
        ],
        "count": 2500,
        "delay": 0.0008,
    },
    {
        "name": "Phase 4: Async Queue Backup",
        "component_id": "QUEUE_EVENTS_01",
        "component_type": "QUEUE",
        "messages": [
            "Consumer lag exceeded 50000 messages",
            "Dead letter queue overflow: 10000+ messages",
            "Producer timeout: broker acknowledgment failed",
        ],
        "count": 1500,
        "delay": 0.001,
    },
    {
        "name": "Phase 5: API Gateway Errors",
        "component_id": "API_GATEWAY_01",
        "component_type": "API",
        "messages": [
            "HTTP 503 rate: 45% of requests in last 60s",
            "Latency p99: 12500ms (SLA threshold: 500ms)",
            "Circuit breaker OPEN for service: user-service",
            "Rate limit exceeded for client: mobile-app",
        ],
        "count": 1500,
        "delay": 0.001,
    },
]


def send_signal_urllib(url, signal):
    """Send signal using urllib (no external deps)."""
    data = json.dumps(signal).encode('utf-8')
    req = urllib.request.Request(
        f"{url}/api/v1/signals/",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except Exception:
        return 0


async def send_signal_httpx(client, url, signal):
    """Send signal using httpx (async)."""
    try:
        resp = await client.post(f"{url}/api/v1/signals/", json=signal, timeout=5.0)
        return resp.status_code
    except Exception:
        return 0


async def run_simulation(url, total_signals):
    print(f"\n{'='*70}")
    print(f"  🚨 IMS FAILURE SIMULATION")
    print(f"  Target: {url}")
    print(f"  Total signals to send: {total_signals:,}")
    print(f"{'='*70}\n")

    stats = {"sent": 0, "accepted": 0, "rate_limited": 0, "failed": 0}
    start = time.time()

    if USE_HTTPX:
        async with httpx.AsyncClient() as client:
            for scenario in FAILURE_SCENARIOS:
                count = int(total_signals * scenario["count"] / 11000)
                print(f"\n▶ {scenario['name']} ({count} signals)")

                tasks = []
                for i in range(count):
                    signal = {
                        "component_id": scenario["component_id"],
                        "component_type": scenario["component_type"],
                        "message": random.choice(scenario["messages"]),
                        "payload": {
                            "error_code": random.randint(1000, 9999),
                            "host": f"node-{random.randint(1, 5)}",
                            "region": random.choice(["us-east-1", "eu-west-1", "ap-south-1"]),
                        },
                    }
                    tasks.append(send_signal_httpx(client, url, signal))

                    if len(tasks) >= 50:
                        results = await asyncio.gather(*tasks)
                        for r in results:
                            stats["sent"] += 1
                            if r == 202: stats["accepted"] += 1
                            elif r == 429: stats["rate_limited"] += 1
                            else: stats["failed"] += 1
                        tasks = []

                if tasks:
                    results = await asyncio.gather(*tasks)
                    for r in results:
                        stats["sent"] += 1
                        if r == 202: stats["accepted"] += 1
                        elif r == 429: stats["rate_limited"] += 1
                        else: stats["failed"] += 1

                elapsed = time.time() - start
                rate = stats["sent"] / elapsed if elapsed > 0 else 0
                print(f"  ✓ Sent: {stats['sent']:,} | Rate: {rate:.0f}/sec | Accepted: {stats['accepted']:,}")
    else:
        # Sync fallback with urllib
        for scenario in FAILURE_SCENARIOS:
            count = int(total_signals * scenario["count"] / 11000)
            print(f"\n▶ {scenario['name']} ({count} signals)")
            for i in range(count):
                signal = {
                    "component_id": scenario["component_id"],
                    "component_type": scenario["component_type"],
                    "message": random.choice(scenario["messages"]),
                    "payload": {"error_code": random.randint(1000, 9999)},
                }
                r = send_signal_urllib(url, signal)
                stats["sent"] += 1
                if r == 202: stats["accepted"] += 1
                elif r == 429: stats["rate_limited"] += 1
                else: stats["failed"] += 1

                if stats["sent"] % 500 == 0:
                    elapsed = time.time() - start
                    print(f"  Progress: {stats['sent']:,}/{total_signals:,} ({stats['sent']/elapsed:.0f}/sec)")

    elapsed = time.time() - start
    print(f"\n{'='*70}")
    print(f"  📊 SIMULATION COMPLETE")
    print(f"  Duration:      {elapsed:.1f}s")
    print(f"  Total Sent:    {stats['sent']:,}")
    print(f"  Accepted:      {stats['accepted']:,}")
    print(f"  Rate Limited:  {stats['rate_limited']:,}")
    print(f"  Failed:        {stats['failed']:,}")
    print(f"  Throughput:    {stats['sent']/elapsed:.0f} signals/sec")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IMS Failure Simulation")
    parser.add_argument("--url", default=API_URL, help="Backend API URL")
    parser.add_argument("--signals", type=int, default=10000, help="Total signals to send")
    args = parser.parse_args()

    asyncio.run(run_simulation(args.url, args.signals))

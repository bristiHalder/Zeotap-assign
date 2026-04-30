"""
Token-bucket rate limiter for the ingestion API.
Prevents cascading failures from upstream signal floods.
"""

import asyncio
import time
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """
    Token-bucket rate limiter.
    - Tokens refill at `rate` tokens/second.
    - Bucket holds at most `capacity` tokens.
    - Each request consumes 1 token.
    """

    def __init__(self, rate: float = None, capacity: float = None):
        self.rate = rate or settings.RATE_LIMIT_RPS
        self.capacity = capacity or self.rate * 2  # burst allowance
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

        # Metrics
        self.total_allowed = 0
        self.total_rejected = 0

    async def acquire(self) -> bool:
        """Try to acquire a token. Returns True if allowed, False if rate-limited."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= 1:
                self.tokens -= 1
                self.total_allowed += 1
                return True
            else:
                self.total_rejected += 1
                return False

    def get_metrics(self) -> dict:
        """Return rate limiter metrics."""
        return {
            "total_allowed": self.total_allowed,
            "total_rejected": self.total_rejected,
            "current_tokens": round(self.tokens, 2),
            "rate_limit_rps": self.rate,
        }


# Singleton instance
rate_limiter = TokenBucketRateLimiter()

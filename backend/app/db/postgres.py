"""
Async PostgreSQL client using asyncpg with connection pooling and retry logic.
Handles Work Items and RCA records (Source of Truth).
"""

import asyncio
import logging
from typing import Optional

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.POSTGRES_URL,
            min_size=5,
            max_size=20,
            command_timeout=30,
        )
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_schema():
    """Initialize database schema."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS work_items (
                id VARCHAR(36) PRIMARY KEY,
                component_id VARCHAR(255) NOT NULL,
                component_type VARCHAR(50) NOT NULL,
                severity VARCHAR(10) NOT NULL,
                state VARCHAR(20) NOT NULL DEFAULT 'OPEN',
                signal_count INTEGER NOT NULL DEFAULT 1,
                title VARCHAR(500) NOT NULL DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                assigned_to VARCHAR(255),
                mttr_seconds DOUBLE PRECISION,
                first_signal_time TIMESTAMP WITH TIME ZONE
            );

            CREATE INDEX IF NOT EXISTS idx_work_items_state ON work_items(state);
            CREATE INDEX IF NOT EXISTS idx_work_items_severity ON work_items(severity);
            CREATE INDEX IF NOT EXISTS idx_work_items_component_id ON work_items(component_id);
            CREATE INDEX IF NOT EXISTS idx_work_items_created_at ON work_items(created_at DESC);

            CREATE TABLE IF NOT EXISTS rca_records (
                id VARCHAR(36) PRIMARY KEY,
                work_item_id VARCHAR(36) NOT NULL REFERENCES work_items(id),
                incident_start TIMESTAMP WITH TIME ZONE NOT NULL,
                incident_end TIMESTAMP WITH TIME ZONE NOT NULL,
                root_cause_category VARCHAR(100) NOT NULL,
                root_cause_description TEXT NOT NULL,
                fix_applied TEXT NOT NULL,
                prevention_steps TEXT NOT NULL,
                mttr_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                UNIQUE(work_item_id)
            );

            CREATE TABLE IF NOT EXISTS state_transitions (
                id VARCHAR(36) PRIMARY KEY,
                work_item_id VARCHAR(36) NOT NULL REFERENCES work_items(id),
                from_state VARCHAR(20) NOT NULL,
                to_state VARCHAR(20) NOT NULL,
                transitioned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                notes TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_transitions_work_item
                ON state_transitions(work_item_id, transitioned_at DESC);
        """)
    logger.info("PostgreSQL schema initialized successfully")


async def execute_with_retry(query: str, *args, max_retries: int = 3) -> str:
    """Execute a query with exponential backoff retry logic."""
    pool = await get_pool()
    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                return await conn.execute(query, *args)
        except (asyncpg.PostgresConnectionError, OSError) as e:
            if attempt == max_retries - 1:
                logger.error(f"PostgreSQL write failed after {max_retries} retries: {e}")
                raise
            wait = 2 ** attempt * 0.1  # 0.1s, 0.2s, 0.4s
            logger.warning(f"PostgreSQL retry {attempt + 1}/{max_retries}, waiting {wait}s")
            await asyncio.sleep(wait)


async def fetch_with_retry(query: str, *args, max_retries: int = 3):
    """Fetch rows with retry logic."""
    pool = await get_pool()
    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except (asyncpg.PostgresConnectionError, OSError) as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt * 0.1
            await asyncio.sleep(wait)


async def fetchrow_with_retry(query: str, *args, max_retries: int = 3):
    """Fetch single row with retry logic."""
    pool = await get_pool()
    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except (asyncpg.PostgresConnectionError, OSError) as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt * 0.1
            await asyncio.sleep(wait)

"""
Async MongoDB client using Motor.
Stores raw signals (Data Lake / Audit Log).
"""

import asyncio
import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def get_client() -> AsyncIOMotorClient:
    """Get or create MongoDB client."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            maxPoolSize=50,
            serverSelectionTimeoutMS=5000,
        )
    return _client


def get_database() -> AsyncIOMotorDatabase:
    """Get the IMS database."""
    global _db
    if _db is None:
        _db = get_client()[settings.MONGODB_DB_NAME]
    return _db


async def init_indexes():
    """Create MongoDB indexes for efficient querying."""
    db = get_database()
    signals = db["signals"]
    await signals.create_index("component_id")
    await signals.create_index("work_item_id")
    await signals.create_index("timestamp")
    await signals.create_index("component_type")
    await signals.create_index([("component_id", 1), ("timestamp", -1)])
    logger.info("MongoDB indexes created successfully")


async def close_client():
    """Close MongoDB client."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None


async def insert_with_retry(collection_name: str, document: dict, max_retries: int = 3):
    """Insert a document with retry logic."""
    db = get_database()
    collection = db[collection_name]
    for attempt in range(max_retries):
        try:
            result = await collection.insert_one(document)
            return result
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"MongoDB insert failed after {max_retries} retries: {e}")
                raise
            wait = 2 ** attempt * 0.1
            logger.warning(f"MongoDB retry {attempt + 1}/{max_retries}, waiting {wait}s")
            await asyncio.sleep(wait)


async def insert_many_with_retry(collection_name: str, documents: list[dict], max_retries: int = 3):
    """Insert multiple documents with retry logic."""
    db = get_database()
    collection = db[collection_name]
    for attempt in range(max_retries):
        try:
            result = await collection.insert_many(documents)
            return result
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"MongoDB bulk insert failed after {max_retries} retries: {e}")
                raise
            wait = 2 ** attempt * 0.1
            await asyncio.sleep(wait)

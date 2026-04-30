"""
WebSocket endpoint for real-time dashboard updates.
Uses Redis Pub/Sub to push events to connected clients.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db import redis_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Connected WebSocket clients
_clients: set[WebSocket] = set()


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time incident updates.
    Subscribes to Redis Pub/Sub and pushes events to connected clients.
    """
    await websocket.accept()
    _clients.add(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(_clients)}")

    try:
        # Subscribe to Redis events
        r = await redis_client.get_pubsub_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe("incidents")

        # Create task to read from Redis and forward to client
        async def forward_events():
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        await websocket.send_text(message["data"])
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass

        forward_task = asyncio.create_task(forward_events())

        # Keep connection alive and handle client messages
        try:
            while True:
                data = await websocket.receive_text()
                # Client can send "ping" to keep alive
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
        except WebSocketDisconnect:
            pass
        finally:
            forward_task.cancel()
            await pubsub.unsubscribe("incidents")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        _clients.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(_clients)}")

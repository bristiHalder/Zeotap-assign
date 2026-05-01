"""
IMS Backend — FastAPI Application Entry Point.

Mission-Critical Incident Management System for monitoring
distributed infrastructure and managing failure mediation workflow.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import postgres as pg
from app.db import mongodb as mongo
from app.db import redis_client
from app.ingestion.queue import signal_queue
from app.ingestion.processor import process_signal
from app.services.metrics import metrics_service
from app.routes import signals, workitems, rca, health, websocket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan — initializes DB connections, starts workers,
    and handles graceful shutdown.
    """
    logger.info("Starting IMS Backend...")

    # Initialize databases
    logger.info("Connecting to PostgreSQL...")
    await pg.get_pool()
    await pg.init_schema()

    logger.info("Connecting to MongoDB...")
    mongo.get_client()
    await mongo.init_indexes()

    logger.info("Connecting to Redis...")
    await redis_client.get_redis()

    # Start queue workers
    logger.info(f"Starting {settings.WORKER_COUNT} queue workers...")
    await signal_queue.start_workers(process_signal, settings.WORKER_COUNT)

    # Start metrics reporting
    await metrics_service.start()

    logger.info("IMS Backend ready -- accepting signals")

    yield  # Application runs here

    # Graceful shutdown
    logger.info("Shutting down IMS Backend...")
    await signal_queue.stop()
    await metrics_service.stop()
    await pg.close_pool()
    await mongo.close_client()
    await redis_client.close_redis()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Incident Management System",
    description=(
        "Mission-critical IMS for monitoring distributed infrastructure. "
        "Handles high-volume signal ingestion, debouncing, incident workflow, "
        "and mandatory Root Cause Analysis."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "https://project-g6m6a-agr9xy6qx-bristihalders-projects.vercel.app"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register routes
app.include_router(signals.router)
app.include_router(workitems.router)
app.include_router(rca.router)
app.include_router(health.router)
app.include_router(health.dashboard_router)
app.include_router(websocket.router)


@app.get("/")
async def root():
    """API root — basic info."""
    return {
        "service": "Incident Management System",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }

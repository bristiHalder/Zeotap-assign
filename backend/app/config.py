"""
Centralized configuration via pydantic-settings.
All values are configurable via environment variables.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database URLs
    # validation_alias allows Pydantic to look for multiple env var names
    MONGODB_URL: str = Field(
        default="mongodb://mongodb:27017",
        validation_alias="MONGODB_URL"
    )
    MONGODB_DB_NAME: str = "ims_datalake"
    
    POSTGRES_URL: str = Field(
        default="postgresql://ims_user:ims_password@postgres:5432/ims_db",
        validation_alias="DATABASE_URL" # Railway's default
    )
    
    REDIS_URL: str = Field(
        default="redis://redis:6379/0",
        validation_alias="REDIS_URL"
    )

    # Ingestion tuning
    RATE_LIMIT_RPS: int = 5000
    BACKPRESSURE_QUEUE_SIZE: int = 50000
    WORKER_COUNT: int = 4

    # Debouncing
    DEBOUNCE_WINDOW_SEC: int = 10
    DEBOUNCE_THRESHOLD: int = 100

    # Observability
    METRICS_INTERVAL_SEC: int = 5

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

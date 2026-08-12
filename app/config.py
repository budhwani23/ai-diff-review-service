from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_version: str = "1.0.0"
    bearer_token: str = "development-token"
    database_url: str = "sqlite+aiosqlite:///./review.db"
    migration_database_url: str | None = None

    max_payload_bytes: int = 1_048_576
    chunk_bytes: int = 65_536
    max_concurrent_jobs: int = 4
    rate_limit_per_minute: int = 30

    cerebras_api_key: str | None = None
    cerebras_model: str = "gpt-oss-120b"
    cerebras_timeout_seconds: float = Field(default=20.0, gt=0)
    cerebras_max_retries: int = Field(default=1, ge=0, le=5)

    worker_poll_seconds: float = Field(default=0.05, gt=0)
    mock_processing_delay_ms: int = Field(default=0, ge=0)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()

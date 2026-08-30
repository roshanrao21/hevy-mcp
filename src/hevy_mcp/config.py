from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    hevy_api_key: str | None = None
    hevy_base_url: str = "https://api.hevyapp.com"

    mcp_transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    mcp_access_token: str | None = None
    allow_header_hevy_key: bool = False
    allow_writes: bool = False

    request_timeout_seconds: float = Field(default=20, gt=0, le=120)
    max_page_size: int = Field(default=10, ge=1, le=100)
    rate_limit_requests: int = Field(default=60, ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()

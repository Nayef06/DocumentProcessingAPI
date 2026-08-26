from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Async Document Processing API"
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = Field(min_length=32)
    ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)
    UPLOAD_DIR: Path = Path("uploads")
    MAX_UPLOAD_SIZE_MB: int = Field(default=10, gt=0)

    # The shared .env file also contains Docker Compose and test settings that
    # are intentionally not application settings.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

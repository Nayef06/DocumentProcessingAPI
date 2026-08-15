from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Async Document Processing API"
    DEBUG: bool = True
    API_PREFIX: str = "/api"
    DATABASE_URL: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/"
        "async_document_processing"
    )
    SECRET_KEY: str
    ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    UPLOAD_DIR: Path = Path("uploads")
    MAX_UPLOAD_SIZE_MB: int = Field(default=10, gt=0)

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

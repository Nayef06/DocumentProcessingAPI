from typing import Literal

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

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

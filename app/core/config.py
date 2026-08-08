from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Async Document Processing API"
    DEBUG: bool = True
    API_PREFIX: str = "/api"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

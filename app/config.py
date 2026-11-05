from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "mock"
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"

    database_url: str = "postgresql://facturas:facturas@localhost:5432/facturas"
    umbral_confianza: float = 0.8

    google_credentials_file: str = ""
    google_share_with: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

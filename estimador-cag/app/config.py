from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Proveedor primario. Anthropic por defecto.
    LLM_PROVIDER: str = "anthropic"
    LLM_MODEL: str = "claude-haiku-4-5-20251001"

    # Proveedor de respaldo: se usa solo si el primario falla. Déjalo vacío para
    # desactivar el fallback.
    LLM_FALLBACK_PROVIDER: str | None = "openai"
    LLM_FALLBACK_MODEL: str | None = "gpt-4o-mini"

    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    OPEN_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str
    LLM_PROVIDER: str
    LLM_MODEL: str
    APP_ENV: str
    LOG_LEVEL: str

@lru_cache
def get_settings() -> Settings:
    return Settings()


class EstimationRequest(BaseModel):
    transcription: str 


class EstimationResponse(BaseModel):
    estimation: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ContextExample(BaseModel):
    meeting_summary: str
    estimation: str


class ContextResponse(BaseModel):
    """The static context (CAG) that is injected into every estimation call."""

    system_prompt: str
    provider: str
    model: str
    examples: list[ContextExample]


class ApiResponse(BaseModel):
    message: str
    status_code: int    
"""Central configuration, loaded from environment / .env."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://precode:precode_dev@localhost:5433/precode"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Accept postgres:// / postgresql:// URLs (e.g. Render Postgres' built-in
        connection string) and route everything through the psycopg3 dialect."""
        if not isinstance(v, str) or v.startswith("postgresql+psycopg://"):
            return v
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    # LLM (any OpenAI-compatible API; empty key => deterministic fallback agent)
    openai_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Server-side voice models (optional; UI falls back to browser speech)
    stt_model: str = "whisper-1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"

    # Seed data anchors relative to today so demos always look live
    demo_supervisor_name: str = "Dave Marsh"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

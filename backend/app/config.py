"""Application settings, loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Groq / LLM ---
    groq_api_key: str = ""

    # gemma2-9b-it is the model mandated by the assignment. It has no native
    # tool-calling support on Groq, so it is used for all extraction and
    # reasoning work via strict JSON prompting.
    primary_model: str = "gemma2-9b-it"

    # llama-3.3-70b-versatile *does* support native tool calling on Groq, so it
    # drives the LangGraph router node (the assignment explicitly allows it
    # "for context"). See docs/ARCHITECTURE.md for the rationale.
    router_model: str = "llama-3.3-70b-versatile"

    llm_temperature: float = 0.2
    llm_max_retries: int = 2

    # --- Database ---
    # Postgres:  postgresql+psycopg://user:pass@localhost:5432/aivoa
    # MySQL:     mysql+pymysql://user:pass@localhost:3306/aivoa
    # SQLite fallback keeps the app runnable before a server is provisioned.
    database_url: str = "sqlite+pysqlite:///./aivoa.db"

    # --- Server ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Uploads ---
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        """False when no Groq key is configured — the app then runs on the
        deterministic fallback extractor so it is still demoable offline."""
        return bool(self.groq_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

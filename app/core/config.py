from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- app ---
    app_name: str = "sourcing-agent"
    deployment_env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # --- database ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sourcing"

    # --- redis / celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- LLM providers ---
    # Provider is selected by deployment_env unless llm_provider is set explicitly.
    llm_provider: Literal["anthropic", "openai", "groq", "ollama"] | None = None
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Model names per provider
    anthropic_model: str = "claude-sonnet-4-6"
    openai_model: str = "gpt-4o"
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_model: str = "llama3.1"

    # --- Amazon data provider ---
    amazon_provider: Literal["keepa", "sp_api", "mock"] = "mock"
    keepa_api_key: str = ""

    # --- research limits ---
    max_research_iterations: int = 6
    max_candidates_per_csv: int = 5000
    research_concurrency: int = 25

    @property
    def resolved_llm_provider(self) -> str:
        if self.llm_provider:
            return self.llm_provider
        # Default policy: cheap/fast in dev, capable in prod.
        return "groq" if self.deployment_env == "dev" else "anthropic"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

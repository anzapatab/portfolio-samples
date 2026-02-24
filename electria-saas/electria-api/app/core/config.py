"""
Application configuration using Pydantic Settings.
Loads from environment variables with validation.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App Configuration
    app_name: str = "electria"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    secret_key: str = Field(..., min_length=32)

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Default Country
    default_country_code: str = "cl"

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str | None = None

    # Anthropic (Claude)
    anthropic_api_key: str
    claude_model_chat: str = "claude-sonnet-4-20250514"
    claude_model_fast: str = "claude-haiku-3-5-20241022"
    claude_max_tokens: int = 1024
    claude_temperature: float = 0.1

    # OpenAI (Embeddings)
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dimensions: int = 3072

    # Cohere (Reranking)
    cohere_api_key: str | None = None
    cohere_rerank_model: str = "rerank-english-v3.0"

    # Pinecone
    pinecone_api_key: str
    pinecone_environment: str = "us-east-1"
    pinecone_index_name: str = "electria-docs"
    pinecone_namespace_prefix: str = "cl"

    # Cloudflare R2
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str = "electria-documents"
    r2_public_url: str | None = None

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # Email (Resend)
    resend_api_key: str | None = None
    email_from: str = "ELECTRIA <noreply@electria.cl>"

    # Stripe
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_starter: str | None = None
    stripe_price_professional: str | None = None
    stripe_price_business: str | None = None

    # Monitoring
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    sentry_dsn: str | None = None

    # External Data Sources
    coordinador_api_url: str = "https://api.coordinador.cl"
    cne_base_url: str = "https://www.cne.cl"
    sec_base_url: str = "https://www.sec.cl"

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @computed_field
    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @computed_field
    @property
    def celery_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Use dependency injection in FastAPI routes.
    """
    return Settings()


# Convenience alias
settings = get_settings()

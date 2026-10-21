from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_name: str = "TestMate AI API"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://testmate:testmate@localhost:5432/testmate_ai"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    ai_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    analysis_timeout_seconds: float = 30.0

    # Test Execution Engine (Phase 5)
    target_app_url: str = "http://localhost:5173"
    target_api_url: str = "http://localhost:8000/api/v1"
    approved_api_hosts: str = "localhost,127.0.0.1,testserver"
    browser_headless: bool = True
    browser_timeout_seconds: float = 15.0
    http_timeout_seconds: float = 10.0
    evidence_storage_dir: str = "evidence_storage"

    # Historical Bug Intelligence / Qdrant (Phase 8)
    qdrant_mode: str = "server"  # "server", "local", or "memory"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "testmate_historical_knowledge"
    qdrant_local_path: str = "qdrant_storage"
    qdrant_timeout_seconds: float = 5.0
    qdrant_vector_size: int = 384

    # Embedding Model Configuration (Phase 8.3)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32

    # Historical Bug Intelligence / Semantic Retrieval (Phase 8.6)
    knowledge_retrieval_min_score: float = 0.4
    knowledge_retrieval_limit: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_embedding_and_qdrant_dimensions(self) -> "Settings":
        if self.embedding_dimension != self.qdrant_vector_size:
            raise ValueError(
                f"Configuration mismatch: embedding_dimension ({self.embedding_dimension}) "
                f"must equal qdrant_vector_size ({self.qdrant_vector_size})."
            )
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_api_hosts(self) -> list[str]:
        return [host.strip().lower() for host in self.approved_api_hosts.split(",") if host.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

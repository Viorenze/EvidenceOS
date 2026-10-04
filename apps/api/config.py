"""Application configuration management using Pydantic Settings.

Thresholds, model parameters, and database connection strings are consolidated here
so no business logic hard-codes magic numbers or environment variables directly.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database connection URL (PostgreSQL + pgvector)
    database_url: str = "postgresql+psycopg://evidence:evidence@localhost:5432/evidenceos"

    # Embedding provider selection ("local" or "fake" for offline deterministic tests)
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512

    # LLM configuration (OpenAI-compatible)
    llm_provider: str = "openai"  # "openai" or "fake" for offline deterministic tests
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: float = 30.0

    # RAG parameters (PRD Section 7 & 8)
    chunk_size: int = 500
    chunk_overlap: int = 50
    vector_top_k: int = 20
    fulltext_top_k: int = 20
    rrf_k: int = 60
    final_top_k: int = 5
    max_rewrites: int = 2
    max_generate_retries: int = 1
    fixed_refusal_text: str = "根据已有知识库内容，无法回答该问题。"


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance to avoid reading environment multiple times."""
    return Settings()

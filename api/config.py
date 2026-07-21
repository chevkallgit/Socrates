"""Typed configuration via pydantic-settings.

Every field can be overridden by an environment variable of the same name
(case-insensitive) or by a .env file. `get_settings` is cached so the object
is built once and treated as a singleton — this is the app's config source
of truth.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- ChromaDB ---------------------------------------------------------
    # The FastAPI process is the Single Owner of this store.
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    collection_name: str = "textbook_chunks"

    # --- Embeddings -------------------------------------------------------
    # MUST match the model the extraction pipeline used to embed the chunks,
    # or query/document vectors live in different spaces and distances are junk.
    embedding_model: str = "all-MiniLM-L6-v2"

    # --- Retrieval --------------------------------------------------------
    top_k: int = 5

    # --- Anthropic / RAG generation --------------------------------------
    anthropic_api_key: str = ""
    answer_model: str = "claude-sonnet-4-6"
    max_tokens: int = 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

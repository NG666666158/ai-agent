from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    force_fallback_llm: bool = os.getenv("AGENT_FORCE_FALLBACK", "").lower() in {"1", "true", "yes"}
    allow_online_search: bool = os.getenv("ALLOW_ONLINE_SEARCH", "true").lower() in {"1", "true", "yes"}
    web_search_endpoint: str = os.getenv(
        "WEB_SEARCH_ENDPOINT",
        "https://api.duckduckgo.com/",
    )
    web_search_provider: str = os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo")
    web_search_max_results: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
    web_search_timeout: float = float(os.getenv("WEB_SEARCH_TIMEOUT", "12"))
    request_timeout: float = float(os.getenv("LLM_TIMEOUT", "45"))
    vector_backend: str = os.getenv("VECTOR_BACKEND", "local")
    vector_service_url: str = os.getenv("VECTOR_SERVICE_URL", "http://127.0.0.1:6333")
    vector_collection: str = os.getenv("VECTOR_COLLECTION", "orion_agent_memories")
    vector_api_key: str | None = os.getenv("VECTOR_API_KEY")
    vector_timeout: float = float(os.getenv("VECTOR_TIMEOUT", "8"))
    vector_dimensions: int = int(os.getenv("VECTOR_DIMENSIONS", "1536"))


def get_settings() -> Settings:
    return Settings()

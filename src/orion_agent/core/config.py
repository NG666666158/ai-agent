from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class Settings:
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai").lower())
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    minimax_api_key: str | None = field(default_factory=lambda: os.getenv("MINIMAX_API_KEY"))
    minimax_model: str = field(default_factory=lambda: os.getenv("MINIMAX_MODEL", "MiniMax-M2.7"))
    minimax_base_url: str = field(default_factory=lambda: os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"))
    minimax_max_retries: int = field(default_factory=lambda: int(os.getenv("MINIMAX_MAX_RETRIES", "1")))
    embedding_model: str = field(default_factory=lambda: os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))
    force_fallback_llm: bool = field(
        default_factory=lambda: os.getenv("AGENT_FORCE_FALLBACK", "").lower() in {"1", "true", "yes"}
    )
    allow_online_search: bool = field(
        default_factory=lambda: os.getenv("ALLOW_ONLINE_SEARCH", "true").lower() in {"1", "true", "yes"}
    )
    web_search_endpoint: str = field(
        default_factory=lambda: os.getenv("WEB_SEARCH_ENDPOINT", "https://api.duckduckgo.com/")
    )
    web_search_provider: str = field(default_factory=lambda: os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo"))
    web_search_max_results: int = field(default_factory=lambda: int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5")))
    web_search_timeout: float = field(default_factory=lambda: float(os.getenv("WEB_SEARCH_TIMEOUT", "12")))
    request_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "45")))
    tool_max_retries: int = field(default_factory=lambda: int(os.getenv("AGENT_TOOL_MAX_RETRIES", "1")))
    replan_limit: int = field(default_factory=lambda: int(os.getenv("AGENT_REPLAN_LIMIT", "1")))
    vector_backend: str = field(default_factory=lambda: os.getenv("VECTOR_BACKEND", "local"))
    vector_service_url: str = field(default_factory=lambda: os.getenv("VECTOR_SERVICE_URL", "http://127.0.0.1:6333"))
    vector_collection: str = field(default_factory=lambda: os.getenv("VECTOR_COLLECTION", "orion_agent_memories"))
    vector_api_key: str | None = field(default_factory=lambda: os.getenv("VECTOR_API_KEY"))
    vector_timeout: float = field(default_factory=lambda: float(os.getenv("VECTOR_TIMEOUT", "8")))
    vector_dimensions: int = field(default_factory=lambda: int(os.getenv("VECTOR_DIMENSIONS", "1536")))


def get_settings() -> Settings:
    return Settings()

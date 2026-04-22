from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_LOADED = False


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
    execution_recovery_retries: int = field(
        default_factory=lambda: int(os.getenv("AGENT_EXECUTION_RECOVERY_RETRIES", "1"))
    )
    vector_backend: str = field(default_factory=lambda: os.getenv("VECTOR_BACKEND", "local"))
    vector_service_url: str = field(default_factory=lambda: os.getenv("VECTOR_SERVICE_URL", "http://127.0.0.1:6333"))
    vector_collection: str = field(default_factory=lambda: os.getenv("VECTOR_COLLECTION", "orion_agent_memories"))
    vector_api_key: str | None = field(default_factory=lambda: os.getenv("VECTOR_API_KEY"))
    vector_timeout: float = field(default_factory=lambda: float(os.getenv("VECTOR_TIMEOUT", "8")))
    vector_dimensions: int = field(default_factory=lambda: int(os.getenv("VECTOR_DIMENSIONS", "1536")))
    context_budget_session_summary: int = field(default_factory=lambda: int(os.getenv("CONTEXT_BUDGET_SESSION_SUMMARY", "1200")))
    context_budget_recent_messages: int = field(default_factory=lambda: int(os.getenv("CONTEXT_BUDGET_RECENT_MESSAGES", "6")))
    context_budget_condensed_recent_messages: int = field(default_factory=lambda: int(os.getenv("CONTEXT_BUDGET_CONDENSED_RECENT_MESSAGES", "3")))
    context_budget_recalled_memories: int = field(default_factory=lambda: int(os.getenv("CONTEXT_BUDGET_RECALLED_MEMORIES", "5")))
    context_budget_profile_facts: int = field(default_factory=lambda: int(os.getenv("CONTEXT_BUDGET_PROFILE_FACTS", "6")))
    context_budget_working_memory: int = field(default_factory=lambda: int(os.getenv("CONTEXT_BUDGET_WORKING_MEMORY", "8")))
    context_budget_source_summary: int = field(default_factory=lambda: int(os.getenv("CONTEXT_BUDGET_SOURCE_SUMMARY", "600")))


def load_project_env(*, project_root: Path | None = None, force: bool = False) -> None:
    """Load deploy/.env into os.environ without overriding explicit environment values."""
    global _ENV_LOADED

    if _ENV_LOADED and not force:
        return

    root = project_root or PROJECT_ROOT
    env_path = root / "deploy" / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

    _ENV_LOADED = True


def get_settings() -> Settings:
    load_project_env()
    return Settings()

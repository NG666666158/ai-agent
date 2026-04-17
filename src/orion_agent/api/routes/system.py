from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from orion_agent.core.config import get_settings
from orion_agent.core.models import UserProfileMergeRequest, UserProfileUpdateRequest
from orion_agent.dependencies import agent_service


router = APIRouter(tags=["system"])


@router.get("/system/runtime")
def runtime_settings():
    settings = get_settings()
    return {
        "llm_provider": settings.llm_provider,
        "openai_model": settings.openai_model,
        "minimax_model": settings.minimax_model,
        "minimax_base_url": settings.minimax_base_url,
        "embedding_model": settings.embedding_model,
        "force_fallback_llm": settings.force_fallback_llm,
        "allow_online_search": settings.allow_online_search,
        "web_search_provider": settings.web_search_provider,
        "web_search_endpoint": settings.web_search_endpoint,
        "web_search_max_results": settings.web_search_max_results,
        "vector_backend": settings.vector_backend,
        "vector_service_url": settings.vector_service_url,
        "vector_collection": settings.vector_collection,
    }


@router.get("/system/health")
def runtime_health():
    runtime = agent_service.runtime_summary()
    return {
        "llm_mode": runtime["llm_mode"],
        "llm_provider": runtime["llm_provider"],
        "llm_last_error": runtime["llm_last_error"],
        "embedding_mode": runtime["embedding_mode"],
        "embedding_provider": runtime["embedding_provider"],
        "search_mode": "online" if get_settings().allow_online_search else "disabled",
        "vector_backend": runtime["vector_backend"],
        "vector_status": runtime["vector_status"],
        "tools": [tool.name for tool in agent_service.list_tools()],
    }


@router.get("/system/llm-probe")
def llm_probe(perform_request: bool = False):
    return agent_service.probe_llm(perform_request=perform_request)


@router.get("/system/profile")
def user_profile(
    limit: int = Query(default=50, ge=1, le=200),
    include_inactive: bool = False,
):
    return agent_service.list_user_profile_facts(limit=limit, include_inactive=include_inactive)


@router.put("/system/profile/{fact_id}")
def update_user_profile(fact_id: str, payload: UserProfileUpdateRequest):
    updated = agent_service.update_user_profile_fact(fact_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Profile fact not found")
    return updated


@router.post("/system/profile/{fact_id}/merge")
def merge_user_profile(fact_id: str, payload: UserProfileMergeRequest):
    merged = agent_service.merge_user_profile_fact(fact_id, payload)
    if merged is None:
        raise HTTPException(status_code=404, detail="Profile fact not found")
    return merged


@router.get("/system/metrics", response_class=PlainTextResponse)
def runtime_metrics():
    runtime = agent_service.runtime_summary()
    return "\n".join(
        [
            "# HELP orion_tasks_total Total tasks stored by the agent",
            "# TYPE orion_tasks_total gauge",
            f"orion_tasks_total {runtime['task_count']}",
            "# HELP orion_memories_total Total long-term memories stored by the agent",
            "# TYPE orion_memories_total gauge",
            f"orion_memories_total {runtime['memory_count']}",
            "# HELP orion_vector_store_up Vector store health flag",
            "# TYPE orion_vector_store_up gauge",
            f"orion_vector_store_up {1 if runtime['vector_status'] == 'ready' else 0}",
        ]
    )

from fastapi import APIRouter, HTTPException, Query

from orion_agent.core.models import IngestionCommitRequest, IngestionPreviewRequest, MemoryUpdateRequest
from orion_agent.dependencies import agent_service


router = APIRouter(tags=["memories"])


@router.get("/memories")
def list_memories(
    scope: str | None = None,
    query: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return agent_service.list_memories(scope=scope, query=query, limit=limit)


@router.get("/memories/search")
def search_memories(query: str, scope: str = "default", limit: int = Query(default=5, ge=1, le=20)):
    return agent_service.search_memories(query=query, scope=scope, limit=limit)


@router.post("/memories/ingest/preview")
def preview_ingestion(payload: IngestionPreviewRequest):
    return agent_service.preview_ingestion(payload)


@router.post("/memories/ingest/commit")
def commit_ingestion(payload: IngestionCommitRequest):
    return agent_service.commit_ingestion(payload)


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str):
    deleted = agent_service.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True, "memory_id": memory_id}


@router.put("/memories/{memory_id}")
def update_memory(memory_id: str, payload: MemoryUpdateRequest):
    updated = agent_service.update_memory(memory_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return updated

from fastapi import APIRouter, HTTPException, Query

from orion_agent.core.models import ChatSessionDetail, SessionCreateRequest, SessionSummaryRefreshRequest
from orion_agent.dependencies import agent_service


router = APIRouter(tags=["sessions"])


@router.post("/sessions")
def create_session(payload: SessionCreateRequest):
    return agent_service.create_session(payload)


@router.get("/sessions")
def list_sessions(limit: int = Query(default=30, ge=1, le=100)):
    return agent_service.list_sessions(limit=limit)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: str) -> ChatSessionDetail:
    detail = agent_service.get_session(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@router.post("/sessions/{session_id}/refresh-summary", response_model=ChatSessionDetail)
def refresh_session_summary(session_id: str, payload: SessionSummaryRefreshRequest | None = None) -> ChatSessionDetail:
    detail = agent_service.refresh_session_summary(session_id, payload)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail

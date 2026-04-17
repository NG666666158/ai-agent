import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from orion_agent.core.models import TaskApprovalDecisionRequest, TaskCreateRequest, TaskResponse, TaskResumeRequest
from orion_agent.dependencies import agent_service


router = APIRouter(tags=["tasks"])


@router.post("/tasks", response_model=TaskResponse)
def create_task(payload: TaskCreateRequest) -> TaskResponse:
    return agent_service.create_and_run_task(payload)


@router.post("/tasks/launch", response_model=TaskResponse)
def launch_task(payload: TaskCreateRequest) -> TaskResponse:
    return agent_service.create_task_async(payload)


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(limit: int = Query(default=20, ge=1, le=100)) -> list[TaskResponse]:
    return agent_service.list_tasks(limit=limit)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    task = agent_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/confirm", response_model=TaskResponse)
def confirm_task_action(task_id: str, payload: TaskApprovalDecisionRequest) -> TaskResponse:
    task = agent_service.confirm_task_action(task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/{task_id}/stream")
def stream_task(task_id: str):
    def event_generator():
        for item in agent_service.stream_task_events(task_id):
            yield f"event: {item['event']}\n"
            yield f"data: {json.dumps(item['data'], ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tasks/{task_id}/steps")
def get_task_steps(task_id: str):
    task = agent_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.steps


@router.get("/tasks/{task_id}/evaluation")
def get_task_evaluation(task_id: str):
    evaluation = agent_service.evaluate_task(task_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return evaluation


@router.get("/tasks/{task_id}/trace")
def get_task_trace(task_id: str):
    task = agent_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    session = agent_service.get_session(task.session_id) if task.session_id else None
    return {
        "task": task.model_dump(mode="json"),
        "session": session.model_dump(mode="json") if session is not None else None,
        "memory_ids": [item.id for item in task.recalled_memories],
        "tool_count": len(task.tool_invocations),
    }


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(task_id: str) -> TaskResponse:
    task = agent_service.cancel_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/resume", response_model=TaskResponse)
def resume_task(task_id: str, payload: TaskResumeRequest | None = None) -> TaskResponse:
    task = agent_service.resume_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tools")
def list_tools():
    return agent_service.list_tools()

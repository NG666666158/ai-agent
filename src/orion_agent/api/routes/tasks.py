from fastapi import APIRouter, HTTPException, Query

from orion_agent.core.models import TaskCreateRequest, TaskResponse
from orion_agent.dependencies import agent_service


router = APIRouter(tags=["tasks"])


@router.post("/tasks", response_model=TaskResponse)
def create_task(payload: TaskCreateRequest) -> TaskResponse:
    return agent_service.create_and_run_task(payload)


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(limit: int = Query(default=20, ge=1, le=100)) -> list[TaskResponse]:
    return agent_service.list_tasks(limit=limit)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    task = agent_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


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


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(task_id: str) -> TaskResponse:
    task = agent_service.cancel_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tools")
def list_tools():
    return agent_service.list_tools()


@router.get("/memories/search")
def search_memories(query: str, scope: str = "default", limit: int = Query(default=5, ge=1, le=20)):
    return agent_service.search_memories(query=query, scope=scope, limit=limit)

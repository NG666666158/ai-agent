from __future__ import annotations

from orion_agent.core.models import TaskRecord, TaskStatus, utcnow


ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.PARSED, TaskStatus.CANCELLED},
    TaskStatus.PARSED: {TaskStatus.PLANNED, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.PLANNED: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.RUNNING: {
        TaskStatus.WAITING_TOOL,
        TaskStatus.REPLANNING,
        TaskStatus.REFLECTING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.WAITING_TOOL: {
        TaskStatus.RUNNING,
        TaskStatus.REPLANNING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.REPLANNING: {
        TaskStatus.RUNNING,
        TaskStatus.WAITING_TOOL,
        TaskStatus.REFLECTING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.REFLECTING: {TaskStatus.REPLANNING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


class InvalidTaskTransition(ValueError):
    """Raised when an invalid task status transition is requested."""


def transition_task(task: TaskRecord, next_status: TaskStatus) -> TaskRecord:
    allowed = ALLOWED_TASK_TRANSITIONS[task.status]
    if next_status not in allowed:
        raise InvalidTaskTransition(f"Invalid transition: {task.status} -> {next_status}")

    task.status = next_status
    task.updated_at = utcnow()
    return task

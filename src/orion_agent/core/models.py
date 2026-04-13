from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    PARSED = "PARSED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING_TOOL = "WAITING_TOOL"
    REFLECTING = "REFLECTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    TODO = "TODO"
    DOING = "DOING"
    DONE = "DONE"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    RETRYING = "RETRYING"


class ToolPermission(str, Enum):
    SAFE = "SAFE"
    CONFIRM = "CONFIRM"
    RESTRICTED = "RESTRICTED"


class ToolCallStatus(str, Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class TaskCreateRequest(BaseModel):
    goal: str = Field(..., min_length=5, description="User task goal.")
    constraints: list[str] = Field(default_factory=list)
    expected_output: str = Field(default="markdown")
    source_text: str | None = Field(default=None)
    source_path: str | None = Field(default=None)
    enable_web_search: bool = Field(default=True)
    memory_scope: str = Field(default="default")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedGoal(BaseModel):
    goal: str
    constraints: list[str] = Field(default_factory=list)
    expected_output: str = "markdown"
    priority: str = "medium"
    domain: str = "general"
    deliverable_title: str = "Agent 执行结果"


class MemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"mem_{uuid4().hex[:8]}")
    kind: str
    content: str
    created_at: datetime = Field(default_factory=utcnow)


class LongTermMemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"ltm_{uuid4().hex[:8]}")
    scope: str = "default"
    topic: str
    summary: str
    details: str
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    timeout_ms: int = 15_000
    permission_level: ToolPermission = ToolPermission.SAFE


class ToolInvocation(BaseModel):
    id: str = Field(default_factory=lambda: f"tool_{uuid4().hex[:8]}")
    step_id: str
    tool_name: str
    status: ToolCallStatus
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_preview: str | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime = Field(default_factory=utcnow)


class Step(BaseModel):
    id: str = Field(default_factory=lambda: f"step_{uuid4().hex[:8]}")
    name: str
    description: str
    status: StepStatus = StepStatus.TODO
    depends_on: list[str] = Field(default_factory=list)
    tool_name: str | None = None
    output: str | None = None


class TaskReview(BaseModel):
    passed: bool
    summary: str
    checklist: list[str] = Field(default_factory=list)


class TaskRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid4().hex[:10]}")
    title: str
    status: TaskStatus = TaskStatus.CREATED
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    parsed_goal: ParsedGoal | None = None
    steps: list[Step] = Field(default_factory=list)
    result: str | None = None
    memory: list[MemoryEntry] = Field(default_factory=list)
    recalled_memories: list[LongTermMemoryRecord] = Field(default_factory=list)
    tool_invocations: list[ToolInvocation] = Field(default_factory=list)
    review: TaskReview | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    id: str
    title: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    parsed_goal: ParsedGoal | None = None
    steps: list[Step]
    result: str | None = None
    memory: list[MemoryEntry]
    recalled_memories: list[LongTermMemoryRecord]
    tool_invocations: list[ToolInvocation]
    review: TaskReview | None = None

    @classmethod
    def from_record(cls, record: TaskRecord) -> "TaskResponse":
        return cls(**record.model_dump())

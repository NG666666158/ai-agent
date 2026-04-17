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
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    WAITING_TOOL = "WAITING_TOOL"
    REPLANNING = "REPLANNING"
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


class FailureCategory(str, Enum):
    NONE = "NONE"
    INPUT_ERROR = "INPUT_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    REVIEW_FAILED = "REVIEW_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class FailureResolution(str, Enum):
    NONE = "NONE"
    RETRY_CURRENT_STEP = "RETRY_CURRENT_STEP"
    SKIP_FAILED_STEP = "SKIP_FAILED_STEP"
    REPLAN_REMAINING_STEPS = "REPLAN_REMAINING_STEPS"
    REPLAN_FROM_CHECKPOINT = "REPLAN_FROM_CHECKPOINT"
    REQUIRE_USER_ACTION = "REQUIRE_USER_ACTION"
    FAIL_FAST = "FAIL_FAST"


class ReplanReason(str, Enum):
    NONE = "NONE"
    TOOL_FAILURE = "TOOL_FAILURE"
    REVIEW_FEEDBACK = "REVIEW_FEEDBACK"
    USER_INTERRUPT = "USER_INTERRUPT"
    CONTEXT_REFRESH = "CONTEXT_REFRESH"
    RESUME_RECOVERY = "RESUME_RECOVERY"


class TaskPhase(str, Enum):
    QUEUED = "QUEUED"
    CONTEXT = "CONTEXT"
    PARSING = "PARSING"
    MEMORY = "MEMORY"
    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    APPROVAL = "APPROVAL"
    REFLECTION = "REFLECTION"
    REPLANNING = "REPLANNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ChatMessageRole(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class TaskCreateRequest(BaseModel):
    goal: str = Field(..., min_length=1, description="User task goal.")
    constraints: list[str] = Field(default_factory=list)
    expected_output: str = Field(default="markdown")
    source_text: str | None = Field(default=None)
    source_path: str | None = Field(default=None)
    enable_web_search: bool = Field(default=True)
    memory_scope: str = Field(default="default")
    session_id: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskApprovalDecisionRequest(BaseModel):
    approval_id: str
    approved: bool


class TaskResumeRequest(BaseModel):
    force_replan: bool = False
    reason: str | None = None


class SessionCreateRequest(BaseModel):
    title: str | None = None
    source_session_id: str | None = None
    seed_prompt: str | None = None


class SessionSummaryRefreshRequest(BaseModel):
    force: bool = False


class MemoryUpdateRequest(BaseModel):
    scope: str | None = None
    topic: str | None = None
    summary: str | None = None
    details: str | None = None
    tags: list[str] | None = None


class UserProfileFactStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MERGED = "MERGED"
    ARCHIVED = "ARCHIVED"


class UserProfileUpdateRequest(BaseModel):
    label: str | None = None
    value: str | None = None
    confidence: float | None = None
    summary: str | None = None
    status: UserProfileFactStatus | None = None


class UserProfileMergeRequest(BaseModel):
    target_fact_id: str
    summary: str | None = None


class UserProfileFact(BaseModel):
    id: str = Field(default_factory=lambda: f"profile_{uuid4().hex[:8]}")
    user_id: str | None = None
    category: str
    label: str
    value: str
    confidence: float = 0.8
    status: UserProfileFactStatus = UserProfileFactStatus.ACTIVE
    superseded_by: str | None = None
    source_session_id: str | None = None
    source_message_id: str | None = None
    source_task_id: str | None = None
    summary: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


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


class ProgressUpdate(BaseModel):
    id: str = Field(default_factory=lambda: f"progress_{uuid4().hex[:8]}")
    stage: str
    message: str
    detail: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class MemorySource(BaseModel):
    task_id: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    source_type: str = "task_result"


class MemoryVersion(BaseModel):
    version: int = 1
    topic: str
    summary: str
    details: str
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)
    updated_by: str = "system"


class LongTermMemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"ltm_{uuid4().hex[:8]}")
    scope: str = "default"
    user_id: str | None = None
    memory_type: str = "task_result"
    topic: str
    summary: str
    details: str
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] = Field(default_factory=list)
    retrieval_score: float | None = None
    retrieval_reason: str | None = None
    retrieval_channels: list[str] = Field(default_factory=list)
    source: MemorySource = Field(default_factory=MemorySource)
    versions: list[MemoryVersion] = Field(default_factory=list)
    deleted: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    timeout_ms: int = 15_000
    permission_level: ToolPermission = ToolPermission.SAFE
    max_retries: int = 0


class ToolInvocation(BaseModel):
    id: str = Field(default_factory=lambda: f"tool_{uuid4().hex[:8]}")
    step_id: str
    tool_name: str
    status: ToolCallStatus
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_preview: str | None = None
    error: str | None = None
    failure_category: FailureCategory = FailureCategory.NONE
    attempt_count: int = 1
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime = Field(default_factory=utcnow)


class PendingApproval(BaseModel):
    id: str = Field(default_factory=lambda: f"approval_{uuid4().hex[:8]}")
    tool_name: str
    operation: str
    message: str
    risk_note: str
    permission_level: ToolPermission = ToolPermission.CONFIRM
    input_payload: dict[str, Any] = Field(default_factory=dict)
    approved: bool | None = None
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None


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


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:8]}")
    session_id: str
    role: ChatMessageRole
    content: str
    task_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ChatSession(BaseModel):
    id: str = Field(default_factory=lambda: f"session_{uuid4().hex[:8]}")
    title: str
    user_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_task_id: str | None = None
    message_count: int = 0
    context_summary: str = ""
    summary_updated_at: datetime | None = None
    source_session_id: str | None = None
    branched_from_message_id: str | None = None
    profile_snapshot: list[str] = Field(default_factory=list)


class ContextLayer(BaseModel):
    system_instructions: str = ""
    session_summary: str = ""
    recent_messages: list[str] = Field(default_factory=list)
    condensed_recent_messages: list[str] = Field(default_factory=list)
    recalled_memories: list[str] = Field(default_factory=list)
    profile_facts: list[str] = Field(default_factory=list)
    working_memory: list[str] = Field(default_factory=list)
    source_summary: str = ""
    layer_budget: dict[str, int] = Field(default_factory=dict)
    build_notes: list[str] = Field(default_factory=list)
    version: int = 1


class TaskCheckpoint(BaseModel):
    phase: TaskPhase = TaskPhase.QUEUED
    current_stage: str = "queued"
    current_step_id: str | None = None
    last_completed_step_id: str | None = None
    last_completed_step_name: str | None = None
    resume_reason: str | None = None
    context_version: int = 1
    failure_count: int = 0
    recovery_attempt: int = 0
    last_failure_category: FailureCategory = FailureCategory.NONE
    last_failure_resolution: FailureResolution = FailureResolution.NONE
    last_recovery_step_id: str | None = None
    last_recovery_step_name: str | None = None
    last_recovery_note: str | None = None
    resumable: bool = False
    last_saved_at: datetime = Field(default_factory=utcnow)


class ReplanEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"replan_{uuid4().hex[:8]}")
    reason: ReplanReason = ReplanReason.NONE
    summary: str
    detail: str | None = None
    failure_category: FailureCategory = FailureCategory.NONE
    trigger_phase: TaskPhase = TaskPhase.REPLANNING
    checkpoint_stage: str | None = None
    checkpoint_step_id: str | None = None
    resume_from_step_id: str | None = None
    resume_from_step_name: str | None = None
    recovery_strategy: str = "replan"
    created_at: datetime = Field(default_factory=utcnow)


class CitationSource(BaseModel):
    id: str = Field(default_factory=lambda: f"cite_{uuid4().hex[:8]}")
    kind: str
    label: str
    detail: str
    source_record_id: str | None = None
    source_session_id: str | None = None
    source_task_id: str | None = None
    excerpt: str | None = None


class ParagraphCitation(BaseModel):
    id: str = Field(default_factory=lambda: f"pcite_{uuid4().hex[:8]}")
    paragraph_index: int
    paragraph_text: str
    source_ids: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)


class ExecutionNodeArtifact(BaseModel):
    label: str
    content: str


class ExecutionNode(BaseModel):
    id: str = Field(default_factory=lambda: f"node_{uuid4().hex[:8]}")
    kind: str
    title: str
    status: str
    summary: str
    detail: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    artifacts: list[ExecutionNodeArtifact] = Field(default_factory=list)


class ChatSessionDetail(BaseModel):
    session: ChatSession
    messages: list[ChatMessage] = Field(default_factory=list)
    tasks: list["TaskResponse"] = Field(default_factory=list)


class TaskRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid4().hex[:10]}")
    title: str
    user_id: str | None = None
    session_id: str | None = None
    status: TaskStatus = TaskStatus.CREATED
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    parsed_goal: ParsedGoal | None = None
    steps: list[Step] = Field(default_factory=list)
    result: str | None = None
    live_result: str | None = None
    retry_count: int = 0
    replan_count: int = 0
    failure_category: FailureCategory = FailureCategory.NONE
    failure_message: str | None = None
    last_replan_reason: ReplanReason = ReplanReason.NONE
    memory: list[MemoryEntry] = Field(default_factory=list)
    recalled_memories: list[LongTermMemoryRecord] = Field(default_factory=list)
    profile_hits: list[UserProfileFact] = Field(default_factory=list)
    tool_invocations: list[ToolInvocation] = Field(default_factory=list)
    progress_updates: list[ProgressUpdate] = Field(default_factory=list)
    pending_approvals: list[PendingApproval] = Field(default_factory=list)
    review: TaskReview | None = None
    context_layers: ContextLayer = Field(default_factory=ContextLayer)
    checkpoint: TaskCheckpoint = Field(default_factory=TaskCheckpoint)
    replan_history: list[ReplanEvent] = Field(default_factory=list)
    citation_sources: list[CitationSource] = Field(default_factory=list)
    paragraph_citations: list[ParagraphCitation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    id: str
    title: str
    session_id: str | None = None
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    parsed_goal: ParsedGoal | None = None
    steps: list[Step]
    result: str | None = None
    live_result: str | None = None
    retry_count: int = 0
    replan_count: int = 0
    failure_category: FailureCategory = FailureCategory.NONE
    failure_message: str | None = None
    last_replan_reason: ReplanReason = ReplanReason.NONE
    memory: list[MemoryEntry]
    recalled_memories: list[LongTermMemoryRecord]
    profile_hits: list[UserProfileFact]
    tool_invocations: list[ToolInvocation]
    progress_updates: list[ProgressUpdate]
    pending_approvals: list[PendingApproval]
    review: TaskReview | None = None
    context_layers: ContextLayer
    checkpoint: TaskCheckpoint
    replan_history: list[ReplanEvent]
    citation_sources: list[CitationSource]
    paragraph_citations: list[ParagraphCitation]
    execution_nodes: list[ExecutionNode] = Field(default_factory=list)

    @classmethod
    def from_record(cls, record: TaskRecord) -> "TaskResponse":
        payload = record.model_dump()
        payload["execution_nodes"] = build_execution_nodes_v2(record)
        return cls(**payload)


def build_execution_nodes(record: TaskRecord) -> list[ExecutionNode]:
    nodes: list[ExecutionNode] = []

    if record.parsed_goal is not None:
        nodes.append(
            ExecutionNode(
                kind="query_rewrite",
                title="Query 改写与任务标准化",
                status="done" if record.status != TaskStatus.CREATED else "doing",
                summary="系统已将原始问题整理为结构化任务目标。",
                detail=record.parsed_goal.goal,
                started_at=record.created_at,
                artifacts=[
                    ExecutionNodeArtifact(label="原始输入", content=record.title),
                    ExecutionNodeArtifact(
                        label="约束条件",
                        content="\n".join(record.parsed_goal.constraints) or "暂无额外约束",
                    ),
                ],
            )
        )

    if (
        record.context_layers.system_instructions
        or record.context_layers.session_summary
        or record.context_layers.condensed_recent_messages
        or record.context_layers.working_memory
    ):
        nodes.append(
            ExecutionNode(
                kind="prompt_assembly",
                title="上下文分层与 Prompt 拼接",
                status="done",
                summary="系统已完成会话上下文压缩、用户画像注入和提示词拼接。",
                detail="用于最终规划、执行与答案生成的上下文已构建完成。",
                started_at=record.created_at,
                artifacts=[
                    ExecutionNodeArtifact(
                        label="会话摘要",
                        content=record.context_layers.session_summary or "暂无",
                    ),
                    ExecutionNodeArtifact(
                        label="压缩上下文",
                        content="\n".join(record.context_layers.condensed_recent_messages) or "暂无",
                    ),
                    ExecutionNodeArtifact(
                        label="工作记忆",
                        content="\n".join(record.context_layers.working_memory) or "暂无",
                    ),
                    ExecutionNodeArtifact(
                        label="构建说明",
                        content="\n".join(record.context_layers.build_notes) or "暂无",
                    ),
                ],
            )
        )

    if record.recalled_memories:
        nodes.append(
            ExecutionNode(
                kind="vector_retrieval",
                title="向量检索与语义召回",
                status="done",
                summary=f"共召回 {len(record.recalled_memories)} 条长期记忆。",
                detail="系统基于问题语义进行了向量检索和召回打分。",
                started_at=record.created_at,
                artifacts=[
                    ExecutionNodeArtifact(
                        label=memory.topic,
                        content=" | ".join(
                            segment
                            for segment in [
                                f"类型={memory.memory_type}",
                                f"分数={memory.retrieval_score:.2f}" if memory.retrieval_score is not None else None,
                                f"原因={memory.retrieval_reason}" if memory.retrieval_reason else None,
                                f"通道={', '.join(memory.retrieval_channels)}" if memory.retrieval_channels else None,
                                memory.summary,
                            ]
                            if segment
                        ),
                    )
                    for memory in record.recalled_memories[:6]
                ],
            )
        )

    if record.recalled_memories or record.profile_hits or record.context_layers.recent_messages or record.context_layers.source_summary:
        nodes.append(
            ExecutionNode(
                kind="multi_recall",
                title="多路召回与来源整合",
                status="done",
                summary="系统已整合长期记忆、用户画像、近期会话和外部材料。",
                detail="多路来源被统一注入到任务上下文中，为后续规划和答案生成提供依据。",
                started_at=record.created_at,
                artifacts=[
                    ExecutionNodeArtifact(label="长期记忆", content=str(len(record.recalled_memories))),
                    ExecutionNodeArtifact(label="用户画像", content=str(len(record.profile_hits))),
                    ExecutionNodeArtifact(label="最近消息", content=str(len(record.context_layers.recent_messages))),
                    ExecutionNodeArtifact(
                        label="外部材料摘要",
                        content=record.context_layers.source_summary or "暂无",
                    ),
                ],
            )
        )

    for progress in record.progress_updates:
        nodes.append(
            ExecutionNode(
                id=f"progress-node-{progress.id}",
                kind="progress",
                title=progress.message,
                status="done" if record.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED} else "doing",
                summary=progress.stage,
                detail=progress.detail,
                started_at=progress.created_at,
            )
        )

    for step in record.steps:
        nodes.append(
            ExecutionNode(
                id=f"step-node-{step.id}",
                kind="step",
                title=step.name,
                status=step.status.value.lower(),
                summary=step.description,
                detail=step.output,
                started_at=record.created_at,
                artifacts=(
                    [ExecutionNodeArtifact(label="绑定工具", content=step.tool_name)]
                    if step.tool_name
                    else []
                ),
            )
        )

    for tool in record.tool_invocations:
        duration_ms = None
        if tool.started_at and tool.completed_at:
            duration_ms = int((tool.completed_at - tool.started_at).total_seconds() * 1000)
        nodes.append(
            ExecutionNode(
                id=f"tool-node-{tool.id}",
                kind="tool",
                title=tool.tool_name,
                status="done" if tool.status == ToolCallStatus.SUCCESS else "error",
                summary=f"尝试次数 {tool.attempt_count}，失败类型 {tool.failure_category.value}",
                detail=tool.error or tool.output_preview,
                started_at=tool.started_at,
                ended_at=tool.completed_at,
                duration_ms=duration_ms,
                artifacts=[
                    ExecutionNodeArtifact(label="输入参数", content=str(tool.input_payload)),
                    ExecutionNodeArtifact(label="结果预览", content=tool.output_preview or "暂无"),
                ],
            )
        )

    for event in record.replan_history:
        nodes.append(
            ExecutionNode(
                id=f"replan-node-{event.id}",
                kind="recovery",
                title=event.summary,
                status="done",
                summary=f"恢复策略：{event.recovery_strategy}",
                detail=event.detail,
                started_at=event.created_at,
                artifacts=[
                    ExecutionNodeArtifact(label="失败类型", content=event.failure_category.value),
                    ExecutionNodeArtifact(label="恢复起点", content=event.resume_from_step_name or "暂无"),
                ],
            )
        )

    if record.live_result or record.result:
        answer_status = "doing"
        if record.status == TaskStatus.COMPLETED:
            answer_status = "done"
        elif record.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            answer_status = "error"
        nodes.append(
            ExecutionNode(
                kind="answer_generation",
                title="最终回答生成",
                status=answer_status,
                summary="系统正在结合上下文、检索结果和工具输出生成最终回答。",
                detail=(record.live_result or record.result or "")[:1200] or None,
                started_at=record.updated_at,
                artifacts=[
                    ExecutionNodeArtifact(
                        label="当前输出预览",
                        content=(record.live_result or record.result or "暂无输出")[:1200],
                    )
                ],
            )
        )

    if record.review is not None:
        nodes.append(
            ExecutionNode(
                kind="review",
                title="结果复核",
                status="done" if record.review.passed else "error",
                summary=record.review.summary,
                detail="\n".join(record.review.checklist) or None,
                started_at=record.updated_at,
            )
        )

    nodes.sort(
        key=lambda node: (
            node.started_at or node.ended_at or record.created_at,
            node.kind,
            node.title,
        )
    )
    return nodes


def build_execution_nodes_v2(record: TaskRecord) -> list[ExecutionNode]:
    nodes: list[ExecutionNode] = []

    if record.parsed_goal is not None:
        nodes.append(
            ExecutionNode(
                kind="query_rewrite",
                title="Query 改写与任务标准化",
                status="done" if record.status != TaskStatus.CREATED else "doing",
                summary="系统已将原始问题整理为结构化任务目标。",
                detail=record.parsed_goal.goal,
                started_at=record.created_at,
                artifacts=[
                    ExecutionNodeArtifact(label="原始输入", content=record.title),
                    ExecutionNodeArtifact(
                        label="约束条件",
                        content="\n".join(record.parsed_goal.constraints) or "暂无额外约束",
                    ),
                ],
            )
        )

    if (
        record.context_layers.system_instructions
        or record.context_layers.session_summary
        or record.context_layers.condensed_recent_messages
        or record.context_layers.working_memory
    ):
        nodes.append(
            ExecutionNode(
                kind="prompt_assembly",
                title="上下文分层与 Prompt 拼接",
                status="done",
                summary="系统已完成会话上下文压缩、用户画像注入和提示词拼接。",
                detail="用于最终规划、执行与答案生成的上下文已构建完成。",
                started_at=record.created_at,
                artifacts=[
                    ExecutionNodeArtifact(
                        label="会话摘要",
                        content=record.context_layers.session_summary or "暂无",
                    ),
                    ExecutionNodeArtifact(
                        label="压缩上下文",
                        content="\n".join(record.context_layers.condensed_recent_messages) or "暂无",
                    ),
                    ExecutionNodeArtifact(
                        label="工作记忆",
                        content="\n".join(record.context_layers.working_memory) or "暂无",
                    ),
                    ExecutionNodeArtifact(
                        label="构建说明",
                        content="\n".join(record.context_layers.build_notes) or "暂无",
                    ),
                ],
            )
        )

    if record.recalled_memories:
        nodes.append(
            ExecutionNode(
                kind="vector_retrieval",
                title="向量检索与语义召回",
                status="done",
                summary=f"共召回 {len(record.recalled_memories)} 条长期记忆。",
                detail="系统基于问题语义进行了向量检索和召回打分。",
                started_at=record.created_at,
                artifacts=[
                    ExecutionNodeArtifact(
                        label=memory.topic,
                        content=" | ".join(
                            segment
                            for segment in [
                                f"类型={memory.memory_type}",
                                f"分数={memory.retrieval_score:.2f}" if memory.retrieval_score is not None else None,
                                f"原因={memory.retrieval_reason}" if memory.retrieval_reason else None,
                                f"通道={', '.join(memory.retrieval_channels)}" if memory.retrieval_channels else None,
                                memory.summary,
                            ]
                            if segment
                        ),
                    )
                    for memory in record.recalled_memories[:6]
                ],
            )
        )

    if (
        record.recalled_memories
        or record.profile_hits
        or record.context_layers.recent_messages
        or record.context_layers.source_summary
    ):
        nodes.append(
            ExecutionNode(
                kind="multi_recall",
                title="多路召回与来源整合",
                status="done",
                summary="系统已整合长期记忆、用户画像、近期会话和外部材料。",
                detail="多路来源被统一注入到任务上下文中，为后续规划和答案生成提供依据。",
                started_at=record.created_at,
                artifacts=[
                    ExecutionNodeArtifact(label="长期记忆", content=str(len(record.recalled_memories))),
                    ExecutionNodeArtifact(label="用户画像", content=str(len(record.profile_hits))),
                    ExecutionNodeArtifact(label="最近消息", content=str(len(record.context_layers.recent_messages))),
                    ExecutionNodeArtifact(
                        label="外部材料摘要",
                        content=record.context_layers.source_summary or "暂无",
                    ),
                ],
            )
        )

    for progress in record.progress_updates:
        nodes.append(
            ExecutionNode(
                id=f"progress-node-{progress.id}",
                kind="progress",
                title=progress.message,
                status="done" if record.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED} else "doing",
                summary=progress.stage,
                detail=progress.detail,
                started_at=progress.created_at,
            )
        )

    for step in record.steps:
        nodes.append(
            ExecutionNode(
                id=f"step-node-{step.id}",
                kind="step",
                title=step.name,
                status=step.status.value.lower(),
                summary=step.description,
                detail=step.output,
                started_at=record.created_at,
                artifacts=[
                    ExecutionNodeArtifact(label="绑定工具", content=step.tool_name)
                ]
                if step.tool_name
                else [],
            )
        )

    for tool in record.tool_invocations:
        duration_ms = None
        if tool.started_at and tool.completed_at:
            duration_ms = int((tool.completed_at - tool.started_at).total_seconds() * 1000)
        nodes.append(
            ExecutionNode(
                id=f"tool-node-{tool.id}",
                kind="tool",
                title=tool.tool_name,
                status="done" if tool.status == ToolCallStatus.SUCCESS else "error",
                summary=f"尝试次数 {tool.attempt_count}，失败类型 {tool.failure_category.value}",
                detail=tool.error or tool.output_preview,
                started_at=tool.started_at,
                ended_at=tool.completed_at,
                duration_ms=duration_ms,
                artifacts=[
                    ExecutionNodeArtifact(label="输入参数", content=str(tool.input_payload)),
                    ExecutionNodeArtifact(label="结果预览", content=tool.output_preview or "暂无"),
                ],
            )
        )

    for event in record.replan_history:
        nodes.append(
            ExecutionNode(
                id=f"replan-node-{event.id}",
                kind="recovery",
                title=event.summary,
                status="done",
                summary=f"恢复策略：{event.recovery_strategy}",
                detail=event.detail,
                started_at=event.created_at,
                artifacts=[
                    ExecutionNodeArtifact(label="失败类型", content=event.failure_category.value),
                    ExecutionNodeArtifact(label="恢复起点", content=event.resume_from_step_name or "暂无"),
                ],
            )
        )

    if record.live_result or record.result:
        answer_status = "doing"
        if record.status == TaskStatus.COMPLETED:
            answer_status = "done"
        elif record.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            answer_status = "error"
        nodes.append(
            ExecutionNode(
                kind="answer_generation",
                title="最终回答生成",
                status=answer_status,
                summary="系统正在结合上下文、检索结果和工具输出生成最终回答。",
                detail=(record.live_result or record.result or "")[:1200] or None,
                started_at=record.updated_at,
                artifacts=[
                    ExecutionNodeArtifact(
                        label="当前输出预览",
                        content=(record.live_result or record.result or "暂无输出")[:1200],
                    )
                ],
            )
        )

    if record.review is not None:
        nodes.append(
            ExecutionNode(
                kind="review",
                title="结果复核",
                status="done" if record.review.passed else "error",
                summary=record.review.summary,
                detail="\n".join(record.review.checklist) or None,
                started_at=record.updated_at,
            )
        )

    nodes.sort(
        key=lambda node: (
            node.started_at or node.ended_at or record.created_at,
            node.kind,
            node.title,
        )
    )
    return nodes


ChatSessionDetail.model_rebuild()


from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from orion_agent.core.citation_map import CitationMap
from orion_agent.core.config import Settings, get_settings
from orion_agent.core.context_builder import ContextBuilder
from orion_agent.core.recovery_policy import RecoveryPolicy, RecoveryState, RecoveryStateMachine
from orion_agent.core.embedding_runtime import build_embedder
from orion_agent.core.evaluation import EvaluationResult, TaskEvaluator
from orion_agent.core.execution_engine import ExecutionEngine
from orion_agent.core.llm_runtime import BaseLLMClient, build_llm_client
from orion_agent.core.memory import LongTermMemoryManager, TaskMemoryManager
from orion_agent.core.models import (
    ChatMessage,
    ChatMessageRole,
    ChatSession,
    ChatSessionDetail,
    CitationSource,
    ContextLayer,
    ContextTraceEntry,
    FailureCategory,
    FailureResolution,
    LongTermMemoryRecord,
    MemorySource,
    MemoryUpdateRequest,
    MemoryVersion,
    ParsedGoal,
    ParagraphCitation,
    PendingApproval,
    ProgressUpdate,
    ReplanEvent,
    ReplanReason,
    SessionCreateRequest,
    SessionSummaryRefreshRequest,
    TaskApprovalDecisionRequest,
    TaskCheckpoint,
    TaskCreateRequest,
    TaskPhase,
    TaskRecord,
    TaskResponse,
    TaskResumeRequest,
    TaskStatus,
    StepStatus,
    TrimReason,
    UserProfileFact,
    UserProfileMergeRequest,
    UserProfileUpdateRequest,
    utcnow,
)
from orion_agent.core.observability import Timer, log_event
from orion_agent.core.planner import Planner
from orion_agent.core.profile import UserProfileManager
from orion_agent.core.prompts import PromptLibrary
from orion_agent.core.reflection import Reflector
from orion_agent.core.repository import TaskRepository
from orion_agent.core.session_store import SessionStore
from orion_agent.core.state_machine import transition_task
from orion_agent.core.tools import ToolRegistry
from orion_agent.core.vector_store import build_vector_store


class AgentService:
    """Orchestrates parsing, planning, execution, memory, approvals, and review."""

    CONTEXT_BUDGET = {
        "session_summary": 1_200,
        "recent_messages": 6,
        "condensed_recent_messages": 3,
        "recalled_memories": 5,
        "profile_facts": 6,
        "working_memory": 8,
        "source_summary": 600,
    }

    def __init__(
        self,
        repository: TaskRepository | None = None,
        llm_client: BaseLLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = repository or TaskRepository()
        self.prompts = PromptLibrary()
        self.llm_client = llm_client or build_llm_client(self.settings)
        self.embedder = build_embedder(self.settings)
        self.vector_store = build_vector_store(self.settings, self.repository)
        self.memory_manager = TaskMemoryManager()
        self.long_term_memory = LongTermMemoryManager(self.repository, self.embedder, self.vector_store)
        self.profile_manager = UserProfileManager(self.repository)
        self.context_builder = ContextBuilder(self.profile_manager, self.repository)
        self.tool_registry = ToolRegistry(self.settings)
        self.planner = Planner(self.llm_client, self.prompts)
        self.executor = ExecutionEngine(
            self.tool_registry,
            self.memory_manager,
            self.llm_client,
            self.prompts,
            self.settings,
        )
        self.reflector = Reflector(self.llm_client, self.prompts)
        self.evaluator = TaskEvaluator()
        self.recovery_policy = RecoveryPolicy(self.settings)
        self.recovery_state_machine = RecoveryStateMachine(self.recovery_policy, self.settings)
        self.session_store = SessionStore(
            self.repository,
            self.profile_manager,
            self.llm_client,
            self.prompts,
        )
        self._active_runs: dict[str, threading.Thread] = {}
        self._runs_lock = threading.RLock()

    def create_and_run_task(self, request: TaskCreateRequest) -> TaskResponse:
        with Timer("task.run", goal=request.goal, memory_scope=request.memory_scope):
            task = self._create_task_record(request)
            task = self._run_task_flow(task.id, request)
            return TaskResponse.from_record(task)

    def create_task_async(self, request: TaskCreateRequest) -> TaskResponse:
        task = self._create_task_record(request)
        self._launch_worker(task.id, request, self._run_task_in_background)
        return TaskResponse.from_record(task)

    def resume_task(self, task_id: str, payload: TaskResumeRequest | None = None) -> TaskResponse | None:
        task = self.repository.get(task_id)
        if task is None:
            return None
        request = self._restore_request(task)
        if request is None:
            task.failure_category = FailureCategory.VALIDATION_ERROR
            task.failure_message = "Cannot resume task because the original request payload is missing."
            self.repository.save(task)
            return TaskResponse.from_record(task)

        if payload and payload.force_replan:
            self._mark_task_for_replan(
                task,
                reason=ReplanReason.RESUME_RECOVERY,
                summary=payload.reason or "User requested replan during task resume.",
                detail="Task was resumed with force_replan enabled.",
            )
        else:
            task.failure_category = FailureCategory.NONE
            task.failure_message = None
            self._update_checkpoint(task, phase="EXECUTION", stage="resume_requested", resumable=True, resume_reason=payload.reason if payload else "resume")
        self._append_progress(task, "resume", "正在准备恢复任务。", payload.reason if payload else None)
        self.repository.save(task)
        self._wait_for_worker_exit(task.id, timeout=1.0)
        self._launch_worker(task.id, request, self._resume_task_in_background)
        return TaskResponse.from_record(task)

    def get_task(self, task_id: str) -> TaskResponse | None:
        task = self.repository.get(task_id)
        if task is None:
            return None
        return TaskResponse.from_record(task)

    def list_tasks(self, limit: int = 20) -> list[TaskResponse]:
        return [TaskResponse.from_record(task) for task in self.repository.list(limit=limit)]

    def create_session(self, payload: SessionCreateRequest | None = None) -> ChatSession:
        return self.session_store.create_session(payload)

    def list_sessions(self, limit: int = 30) -> list[ChatSession]:
        return self.session_store.list_sessions(limit=limit)

    def list_user_profile_facts(self, limit: int = 50, *, include_inactive: bool = False) -> list[UserProfileFact]:
        return self.profile_manager.list_facts(limit=limit, include_inactive=include_inactive)

    def update_user_profile_fact(self, fact_id: str, request: UserProfileUpdateRequest) -> UserProfileFact | None:
        return self.profile_manager.update_fact(
            fact_id,
            label=request.label,
            value=request.value,
            confidence=request.confidence,
            summary=request.summary,
            status=request.status,
        )

    def merge_user_profile_fact(self, fact_id: str, request: UserProfileMergeRequest) -> UserProfileFact | None:
        return self.profile_manager.merge_fact(fact_id, request.target_fact_id, summary=request.summary)

    def get_session(self, session_id: str, message_limit: int = 100, task_limit: int = 50) -> ChatSessionDetail | None:
        return self.session_store.get_session(session_id, message_limit=message_limit, task_limit=task_limit)

    def refresh_session_summary(self, session_id: str, payload: SessionSummaryRefreshRequest | None = None) -> ChatSessionDetail | None:
        return self.session_store.refresh_session_summary(session_id, payload)

    def list_memories(self, scope: str | None = None, query: str | None = None, limit: int = 50) -> list[LongTermMemoryRecord]:
        return self.repository.list_long_term_memories(scope=scope, query=query, limit=limit)

    def update_memory(self, memory_id: str, request: MemoryUpdateRequest) -> LongTermMemoryRecord | None:
        return self.long_term_memory.update(
            memory_id,
            scope=request.scope,
            topic=request.topic,
            summary=request.summary,
            details=request.details,
            tags=request.tags,
        )

    def delete_memory(self, memory_id: str) -> bool:
        return self.repository.delete_long_term_memory(memory_id)

    def stream_task_events(self, task_id: str, poll_interval: float = 0.18):
        last_signature: tuple[str, str, int, int, str, str, int, str, int] | None = None
        while True:
            task = self.get_task(task_id)
            if task is None:
                yield {"event": "error", "data": {"message": "Task not found", "task_id": task_id}}
                break
            signature = (
                task.status.value,
                task.updated_at.isoformat(),
                len(task.progress_updates),
                len(task.tool_invocations),
                task.result or "",
                task.live_result or "",
                len(task.pending_approvals),
                task.checkpoint.current_stage,
                task.replan_count,
            )
            if signature != last_signature:
                last_signature = signature
                event_name = "completed" if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED} else "task_update"
                yield {"event": event_name, "data": task.model_dump(mode="json")}
                if event_name == "completed":
                    break
            time.sleep(poll_interval)
    def cancel_task(self, task_id: str) -> TaskResponse | None:
        task = self.repository.get(task_id)
        if task is None:
            return None
        if task.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            transition_task(task, TaskStatus.CANCELLED)
            self._append_progress(task, "cancelled", "任务已取消。")
            self._update_checkpoint(task, phase="CANCELLED", stage="cancelled", resumable=True, resume_reason="manual_cancel")
            self.repository.save(task)
        return TaskResponse.from_record(task)

    def confirm_task_action(self, task_id: str, decision: TaskApprovalDecisionRequest) -> TaskResponse | None:
        task = self.repository.get(task_id)
        request = self._restore_request(task) if task else None
        if task is None or request is None:
            return None
        approval = next((item for item in task.pending_approvals if item.id == decision.approval_id), None)
        if approval is None or approval.approved is not None:
            return TaskResponse.from_record(task)
        approval.approved = decision.approved
        approval.resolved_at = task.updated_at
        if not decision.approved:
            task.failure_category = FailureCategory.PERMISSION_DENIED
            task.failure_message = f"User rejected operation: {approval.operation}"
            transition_task(task, TaskStatus.CANCELLED)
            self._append_progress(task, "approval", "用户拒绝了高风险操作。", approval.message)
            self._update_checkpoint(task, phase="APPROVAL", stage="approval_rejected", resumable=True, resume_reason="approval_rejected")
            self.repository.save(task)
            return TaskResponse.from_record(task)
        transition_task(task, TaskStatus.RUNNING)
        self._append_progress(task, "approval", "高风险操作已获确认。", approval.message)
        self._update_checkpoint(
            task,
            phase="APPROVAL",
            stage="approval_confirmed",
            current_step_id=task.checkpoint.current_step_id,
            resumable=True,
            resume_reason="approval_confirmed",
        )
        self.repository.save(task)
        self._launch_worker(task_id, request, self._resume_after_approval)
        return TaskResponse.from_record(task)

    def list_tools(self):
        return self.tool_registry.list_definitions()

    def search_memories(self, query: str, scope: str = "default", limit: int = 5) -> list[LongTermMemoryRecord]:
        return self.long_term_memory.recall(query=query, scope=scope, limit=limit)

    def evaluate_task(self, task_id: str) -> EvaluationResult | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        return self.evaluator.evaluate(task)

    def runtime_summary(self) -> dict[str, object]:
        vector_health = self.vector_store.health()
        llm_health = self.llm_client.health()
        embedding_health = self.embedder.health()
        return {
            "task_count": self.repository.count_tasks(),
            "memory_count": self.repository.count_long_term_memories(),
            "session_count": self.repository.count_sessions(),
            "vector_backend": vector_health["backend"],
            "vector_status": vector_health["status"],
            "llm_provider": llm_health["provider"],
            "llm_mode": llm_health["mode"],
            "llm_last_error": llm_health.get("last_error", ""),
            "embedding_provider": embedding_health["provider"],
            "embedding_mode": embedding_health["mode"],
        }

    def probe_llm(self, perform_request: bool = False) -> dict[str, object]:
        provider = self.settings.llm_provider
        has_key = bool(self.settings.minimax_api_key if provider == "minimax" else self.settings.openai_api_key)
        configured = has_key or provider == "fallback" or self.settings.force_fallback_llm
        active = self.llm_client.health()
        payload: dict[str, object] = {
            "provider": provider,
            "configured": configured,
            "has_api_key": has_key,
            "forced_fallback": self.settings.force_fallback_llm,
            "active_provider": active["provider"],
            "active_mode": active["mode"],
            "active_last_error": active.get("last_error", ""),
            "model": self.settings.minimax_model if provider == "minimax" else self.settings.openai_model,
        }
        if provider == "minimax":
            payload["base_url"] = self.settings.minimax_base_url
        payload["status"] = "configured" if configured and not perform_request else payload.get("status", "configured")
        if not configured:
            payload["status"] = "missing_credentials"
            return payload
        if perform_request:
            payload.update(self.llm_client.probe())
        return payload

    def _run_task_in_background(self, task_id: str, request: TaskCreateRequest) -> None:
        try:
            self._run_task_flow(task_id, request)
        finally:
            self._drop_worker(task_id)

    def _resume_task_in_background(self, task_id: str, request: TaskCreateRequest) -> None:
        try:
            task = self.repository.get(task_id)
            if task is None or task.status == TaskStatus.COMPLETED:
                return
            self._append_progress(task, "resume", "正在恢复任务执行。", "将从最近可恢复检查点继续推进。")
            self.repository.save(task)
            self._execute_planned_task(task, request, resume_mode=True)
        finally:
            self._drop_worker(task_id)

    def _resume_after_approval(self, task_id: str, request: TaskCreateRequest) -> None:
        try:
            task = self.repository.get(task_id)
            if task is None:
                return
            self._execute_planned_task(task, request, resume_mode=True)
        finally:
            self._drop_worker(task_id)

    def _drop_worker(self, task_id: str) -> None:
        with self._runs_lock:
            self._active_runs.pop(task_id, None)

    def _wait_for_worker_exit(self, task_id: str, timeout: float = 1.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._runs_lock:
                active = self._active_runs.get(task_id)
                if active is None or not active.is_alive():
                    self._active_runs.pop(task_id, None)
                    return
            time.sleep(0.02)

    def _parse_goal(self, request: TaskCreateRequest, task: TaskRecord | None = None) -> ParsedGoal:
        if task is None:
            task = TaskRecord(title=request.goal, session_id=request.session_id)
        system_prompt, user_prompt = self.prompts.parse_goal_messages(
            request.model_dump_json(indent=2),
            session_context=self._render_context_layers(task.context_layers),
        )
        payload = self.llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        return ParsedGoal.model_validate(payload)

    def _create_task_record(self, request: TaskCreateRequest) -> TaskRecord:
        task = TaskRecord(
            title=request.goal,
            session_id=request.session_id,
            metadata={**request.metadata, "original_request": request.model_dump(mode="json")},
        )
        self._update_checkpoint(task, phase="QUEUED", stage="queued", resumable=True)
        self._append_progress(task, "queued", "任务已创建，准备开始执行。", request.goal)
        self.repository.save(task)
        self._append_session_message(
            task.session_id,
            ChatMessageRole.USER,
            request.goal,
            task_id=task.id,
            session_title_hint=request.goal,
        )
        log_event("task.created", task_id=task.id, goal=request.goal)
        return task

    def _launch_worker(self, task_id: str, request: TaskCreateRequest, target) -> None:
        worker = threading.Thread(target=target, args=(task_id, request), daemon=True, name=f"task-worker-{task_id}")
        with self._runs_lock:
            active = self._active_runs.get(task_id)
            if active and active.is_alive():
                return
            self._active_runs[task_id] = worker
        worker.start()
    def _run_task_flow(self, task_id: str, request: TaskCreateRequest) -> TaskRecord:
        task = self.repository.get(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")

        task.context_layers = self._build_context_layers(request)
        self._append_progress(task, "context", "正在加载上下文分层。", self._render_context_layers(task.context_layers)[:240])
        self._update_checkpoint(task, phase="CONTEXT", stage="context_ready", resumable=True, context_version=task.context_layers.version)
        self.repository.save(task)

        self._append_progress(task, "thinking", "正在读取输入任务。")
        self._append_progress(task, "thinking", "正在解析输入内容。", "提取目标、约束、输出格式和领域标签。")
        self.repository.save(task)

        task.parsed_goal = self._parse_goal(request, task)
        self.memory_manager.write(task, "user_goal", request.goal)
        transition_task(task, TaskStatus.PARSED)
        self._update_checkpoint(task, phase="PARSING", stage="parsed", resumable=True, context_version=task.context_layers.version)
        self._append_progress(task, "thinking", "正在整理约束。", "已完成目标解析，开始归纳约束条件和期望输出。")
        self._append_progress(task, "thinking", "正在确认任务重点。", task.parsed_goal.goal)
        self.repository.save(task)

        self._append_progress(task, "memory", "正在检索记忆。", f"记忆作用域：{request.memory_scope}")
        self.repository.save(task)

        RECALLED_MEMORIES_LIMIT = 5
        PROFILE_HITS_LIMIT = 4
        task.recalled_memories = self.long_term_memory.recall(query=request.goal, scope=request.memory_scope, limit=RECALLED_MEMORIES_LIMIT)
        task.profile_hits = self.profile_manager.match_relevant(request.goal, limit=PROFILE_HITS_LIMIT)
        task.context_layers.recalled_memories = [
            self._format_recalled_memory_context(item) for item in task.recalled_memories
        ]
        if task.context_layers.budget_usage:
            task.context_layers.budget_usage.recalled_memories_count = len(task.recalled_memories)
            recalled_trim_reason = TrimReason.COMPRESSED if len(task.recalled_memories) >= RECALLED_MEMORIES_LIMIT else TrimReason.NONE
            task.context_layers.budget_usage.recalled_memories_trim_reason = recalled_trim_reason
            task.context_layers.budget_usage.profile_facts_count = len(task.profile_hits)
            profile_trim_reason = TrimReason.COMPRESSED if len(task.profile_hits) >= PROFILE_HITS_LIMIT else TrimReason.NONE
            task.context_layers.budget_usage.profile_facts_trim_reason = profile_trim_reason
            # Add trace entry for recalled_memories layer (profile_facts trace already added in build())
            task.context_layers.trace_entries.append(
                ContextTraceEntry(
                    layer="recalled_memories",
                    source="long_term_memory",
                    source_id=None,
                    message=f"limit={RECALLED_MEMORIES_LIMIT}, count={len(task.recalled_memories)}, reason={recalled_trim_reason.value}",
                )
            )
        task.context_layers.profile_facts = [f"{item.label}: {item.value}" for item in task.profile_hits]
        self.memory_manager.write(task, "memory_scope", request.memory_scope)
        self._append_progress(
            task,
            "memory",
            "已完成记忆检索。",
            f"召回到 {len(task.recalled_memories)} 条长期记忆，命中 {len(task.profile_hits)} 条用户画像。",
        )
        self._update_checkpoint(task, phase="MEMORY", stage="memory_recalled", resumable=True, context_version=task.context_layers.version)
        self.repository.save(task)

        self._append_progress(task, "planning", "正在生成执行计划。", "开始组合步骤顺序、工具使用和结果产出方式。")
        self.repository.save(task)

        task.steps = self.planner.build_plan(
            parsed_goal=task.parsed_goal,
            recalled_memories=task.recalled_memories,
            source_available=bool(request.source_text or request.source_path),
            enable_web_search=request.enable_web_search,
        )
        transition_task(task, TaskStatus.PLANNED)
        self._update_checkpoint(task, phase="PLANNING", stage="planned", resumable=True, context_version=task.context_layers.version)
        self._append_progress(task, "planning", "正在整理步骤结构。", "把任务拆成可执行步骤并绑定工具。")
        self._append_progress(task, "planning", "执行计划已生成。", f"共规划了 {len(task.steps)} 个步骤。")
        self.repository.save(task)

        if self._pause_for_required_approval(task, request):
            self.repository.save(task)
            return task
        return self._execute_planned_task(task, request)

    def _execute_planned_task(self, task: TaskRecord, request: TaskCreateRequest, *, resume_mode: bool = False) -> TaskRecord:
        if task.status != TaskStatus.RUNNING:
            transition_task(task, TaskStatus.RUNNING)
        self._append_progress(
            task,
            "running",
            "开始执行任务。" if not resume_mode else "正在从检查点恢复执行。",
            "系统将依次推进各个步骤并持续回传进度。",
        )
        self._update_checkpoint(task, phase="EXECUTION", stage="running", resumable=True, context_version=task.context_layers.version)
        self.repository.save(task)

        task = self._run_executor_with_recovery(task, request)
        if task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            self._finalize_task(task, request)
            return task

        transition_task(task, TaskStatus.REFLECTING)
        self._update_checkpoint(task, phase="REFLECTION", stage="reflecting", resumable=True, context_version=task.context_layers.version)
        self._append_progress(task, "review", "正在复核结果质量。", "检查覆盖度、结构完整性与可执行性。")
        self.repository.save(task)

        task.review = self.reflector.review(task, task.parsed_goal)
        if task.review.passed:
            transition_task(task, TaskStatus.COMPLETED)
            self._update_checkpoint(task, phase="COMPLETED", stage="completed", resumable=False, context_version=task.context_layers.version)
            self._append_progress(task, "completed", "任务执行完成。", task.review.summary)
        elif task.replan_count < self.settings.replan_limit:
            self._mark_task_for_replan(
                task,
                reason=ReplanReason.REVIEW_FEEDBACK,
                summary="评审未通过，正在根据反馈修订结果。",
                detail=task.review.summary,
            )
            self.repository.save(task)

            task = self.executor.revise_after_review(
                task,
                task.parsed_goal,
                request,
                task.recalled_memories,
                review_summary=task.review.summary,
                review_checklist=task.review.checklist,
                on_progress=lambda stage, message, detail=None: self._record_progress(task.id, stage, message, detail),
                on_result_stream=lambda text: self._record_live_result(task.id, text),
                on_task_update=lambda updated_task: self.repository.save(updated_task),
            )
            task.live_result = task.result
            transition_task(task, TaskStatus.REFLECTING)
            self._update_checkpoint(task, phase="REFLECTION", stage="reflecting_after_replan", resumable=True, context_version=task.context_layers.version)
            self._append_progress(task, "review", "正在复核修订后的结果。", "系统已根据评审意见完成一次重规划。")
            self.repository.save(task)

            task.review = self.reflector.review(task, task.parsed_goal)
            if task.review.passed:
                transition_task(task, TaskStatus.COMPLETED)
                self._update_checkpoint(task, phase="COMPLETED", stage="completed", resumable=False, context_version=task.context_layers.version)
                self._append_progress(task, "completed", "任务执行完成。", task.review.summary)
            else:
                task.failure_category = FailureCategory.REVIEW_FAILED
                task.failure_message = task.review.summary
                transition_task(task, TaskStatus.FAILED)
                self._update_checkpoint(task, phase="FAILED", stage="failed_after_review", resumable=True, context_version=task.context_layers.version)
                self._append_progress(task, "failed", "评审未通过，已达到当前重规划上限。", task.review.summary)
        else:
            task.failure_category = FailureCategory.REVIEW_FAILED
            task.failure_message = task.review.summary
            transition_task(task, TaskStatus.FAILED)
            self._update_checkpoint(task, phase="FAILED", stage="failed_review", resumable=True, context_version=task.context_layers.version)
            self._append_progress(task, "failed", "任务执行失败。", task.review.summary if task.review else None)

        self._finalize_task(task, request)
        return task

    def _pause_for_required_approval(self, task: TaskRecord, request: TaskCreateRequest) -> bool:
        if not request.source_path:
            return False
        if any(item.approved is None for item in task.pending_approvals):
            return True
        source_path = str(Path(request.source_path))
        approval = PendingApproval(
            tool_name="read_local_file",
            operation="读取本地文件",
            message=f"任务需要读取本地文件：{source_path}",
            risk_note="文件可能包含敏感信息，继续前需要用户明确确认。",
            input_payload={"path": source_path},
        )
        task.pending_approvals.append(approval)
        transition_task(task, TaskStatus.WAITING_APPROVAL)
        self._update_checkpoint(task, phase="APPROVAL", stage="waiting_approval", current_step_id="bootstrap", resumable=True, resume_reason="awaiting_approval")
        self._append_progress(task, "approval", "等待用户确认高风险操作。", approval.message)
        return True

    def _run_executor_with_recovery(self, task: TaskRecord, request: TaskCreateRequest) -> TaskRecord:
        while True:
            try:
                task = self.executor.run(
                    task,
                    task.parsed_goal,
                    request,
                    task.recalled_memories,
                    on_progress=lambda stage, message, detail=None: self._record_progress(task.id, stage, message, detail),
                    on_result_stream=lambda text: self._record_live_result(task.id, text),
                    on_task_update=lambda updated_task: self.repository.save(updated_task),
                )
            except Exception as exc:
                task.failure_category = FailureCategory.INTERNAL_ERROR
                task.failure_message = str(exc)

            task.live_result = task.result
            self.repository.save(task)

            if task.failure_category == FailureCategory.NONE:
                self.repository.save(task)
                return task

            # Use RecoveryStateMachine as the primary state driver for the recovery flow.
            # transition() validates the state transition and raises InvalidTransitionError
            # if the transition is illegal (should not happen in normal runtime paths).
            recovery_state = self.recovery_state_machine.transition(task, task.failure_category)
            resolution = self._classify_failure_resolution(task, task.failure_category)
            self._record_failure_checkpoint(task, resolution)
            self.repository.save(task)

            if recovery_state == RecoveryState.RETRYING:
                task.checkpoint.recovery_attempt += 1
                self._append_progress(
                    task,
                    "recovery",
                    "正在重试当前步骤。",
                    f"失败类型：{task.failure_category.value}；第 {task.checkpoint.recovery_attempt} 次恢复尝试。",
                )
                self._prepare_current_step_retry(task)
                task.failure_category = FailureCategory.NONE
                task.failure_message = None
                self.repository.save(task)
                continue

            if recovery_state == RecoveryState.SKIPPING:
                task.checkpoint.recovery_attempt += 1
                self._prepare_skip_failed_step(task)
                task.failure_category = FailureCategory.NONE
                task.failure_message = None
                self.repository.save(task)
                continue

            if recovery_state == RecoveryState.REPLANNING_REMAINING and task.replan_count < self.settings.replan_limit:
                task.checkpoint.recovery_attempt += 1
                self._prepare_replan_remaining_steps(task, request)
                task.failure_category = FailureCategory.NONE
                task.failure_message = None
                self.repository.save(task)
                continue

            if recovery_state == RecoveryState.REPLANNING_FULL and task.replan_count < self.settings.replan_limit:
                task.checkpoint.recovery_attempt += 1
                self._prepare_replan_from_failure(task, request)
                task.failure_category = FailureCategory.NONE
                task.failure_message = None
                self.repository.save(task)
                continue

            # USER_ACTION is handled at a higher level (pause_for_required_approval or
            # confirm_task_action), and FAILED is terminal — both reach here when
            # the recovery loop cannot continue.
            self.recovery_state_machine.reset_to_healthy()
            self._finalize_failed_execution(task, resolution)
            self.repository.save(task)
            return task

    def _classify_failure_resolution(self, task: TaskRecord, category: FailureCategory) -> FailureResolution:
        return self.recovery_policy.classify_failure_resolution(task, category)

    def _record_failure_checkpoint(self, task: TaskRecord, resolution: FailureResolution) -> None:
        task.checkpoint.failure_count += 1
        task.checkpoint.last_failure_category = task.failure_category
        task.checkpoint.last_failure_resolution = resolution
        self._append_progress(
            task,
            "failure_classified",
            "已完成失败分类。",
            f"失败类型：{task.failure_category.value}；恢复策略：{resolution.value}；错误信息：{task.failure_message or '无'}",
        )

    def _prepare_current_step_retry(self, task: TaskRecord) -> None:
        failed_step = self.recovery_policy.find_failed_step(task)
        if failed_step is None:
            return
        failed_step.status = StepStatus.TODO
        failed_step.output = None
        task.checkpoint.current_step_id = failed_step.id
        task.checkpoint.current_stage = f"retry:{failed_step.name}"
        self._update_checkpoint(
            task,
            phase="EXECUTION",
            stage="retrying_current_step",
            current_step_id=failed_step.id,
            resumable=True,
            resume_reason="retry_after_failure",
            context_version=task.context_layers.version,
            last_recovery_step_id=failed_step.id,
            last_recovery_step_name=failed_step.name,
            last_recovery_note="重试当前失败步骤",
        )

    def _prepare_replan_from_failure(self, task: TaskRecord, request: TaskCreateRequest) -> None:
        failure_detail = task.failure_message or "执行过程中出现可恢复失败。"
        failed_step = self.recovery_policy.find_failed_step(task)
        self._mark_task_for_replan(
            task,
            reason=ReplanReason.TOOL_FAILURE,
            summary="执行中断，正在从检查点重规划。",
            detail=failure_detail,
            failure_category=task.failure_category,
            resume_from_step_id=failed_step.id if failed_step else None,
            resume_from_step_name=failed_step.name if failed_step else None,
        )

        if task.failure_category in {
            FailureCategory.TOOL_TIMEOUT,
            FailureCategory.NETWORK_ERROR,
            FailureCategory.TOOL_UNAVAILABLE,
        }:
            task.context_layers.working_memory.append("replan_hint=disable_web_search_after_failure")
            task.context_layers.build_notes.append("replan:disable_web_search_after_failure")

        task.context_layers.version = int(time.time())
        task.steps = self.planner.build_plan(
            parsed_goal=task.parsed_goal,
            recalled_memories=task.recalled_memories,
            source_available=bool(request.source_text or request.source_path),
            enable_web_search=request.enable_web_search and task.failure_category not in {
                FailureCategory.TOOL_TIMEOUT,
                FailureCategory.NETWORK_ERROR,
                FailureCategory.TOOL_UNAVAILABLE,
            },
        )
        self._append_progress(
            task,
            "replanning",
            "已根据失败原因重建执行计划。",
            f"新计划共 {len(task.steps)} 个步骤，将从检查点重新推进。",
        )
        transition_task(task, TaskStatus.RUNNING)
        self._update_checkpoint(
            task,
            phase="PLANNING",
            stage="replanned_after_failure",
            resumable=True,
            resume_reason="replanned_after_failure",
            context_version=task.context_layers.version,
            last_recovery_step_id=failed_step.id if failed_step else None,
            last_recovery_step_name=failed_step.name if failed_step else None,
            last_recovery_note="从检查点重建整段计划",
        )

    def _prepare_skip_failed_step(self, task: TaskRecord) -> None:
        failed_step = self.recovery_policy.find_failed_step(task)
        if failed_step is None:
            return
        failed_step.status = StepStatus.SKIPPED
        failed_step.output = failed_step.output or f"步骤已跳过：{task.failure_message or '该步骤失败但允许降级继续执行。'}"
        self._append_progress(
            task,
            "recovery",
            "系统已跳过失败步骤并继续执行。",
            f"跳过步骤：{failed_step.name}；失败类型：{task.failure_category.value}",
        )
        self._update_checkpoint(
            task,
            phase="EXECUTION",
            stage="skipping_failed_step",
            current_step_id=failed_step.id,
            resumable=True,
            resume_reason="skip_failed_step",
            context_version=task.context_layers.version,
            last_recovery_step_id=failed_step.id,
            last_recovery_step_name=failed_step.name,
            last_recovery_note="已跳过失败步骤并继续执行",
        )

    def _prepare_replan_remaining_steps(self, task: TaskRecord, request: TaskCreateRequest) -> None:
        failed_step = self.recovery_policy.find_failed_step(task)
        if failed_step is None:
            self._prepare_replan_from_failure(task, request)
            return

        prefix_steps = self._completed_prefix_steps(task)
        rebuilt_steps = self.planner.build_plan(
            parsed_goal=task.parsed_goal,
            recalled_memories=task.recalled_memories,
            source_available=bool(request.source_text or request.source_path),
            enable_web_search=request.enable_web_search,
        )
        start_index = len(prefix_steps)
        remaining_steps = rebuilt_steps[start_index:] if start_index < len(rebuilt_steps) else []
        if not remaining_steps:
            remaining_steps = rebuilt_steps

        self._mark_task_for_replan(
            task,
            reason=ReplanReason.TOOL_FAILURE,
            summary="系统正在重建失败步骤之后的执行计划。",
            detail=f"恢复起点：{failed_step.name}",
            failure_category=task.failure_category,
            resume_from_step_id=failed_step.id,
            resume_from_step_name=failed_step.name,
        )
        task.steps = [*prefix_steps, *remaining_steps]
        task.context_layers.version = int(time.time())
        task.context_layers.build_notes.append(f"replan:remaining_from={failed_step.name}")
        self._append_progress(
            task,
            "replanning",
            "已重建后半段计划。",
            f"保留前置已完成步骤 {len(prefix_steps)} 个，从 {failed_step.name} 开始继续。",
        )
        transition_task(task, TaskStatus.RUNNING)
        self._update_checkpoint(
            task,
            phase="PLANNING",
            stage="replanned_remaining_steps",
            current_step_id=failed_step.id,
            resumable=True,
            resume_reason="replan_remaining_steps",
            context_version=task.context_layers.version,
            last_recovery_step_id=failed_step.id,
            last_recovery_step_name=failed_step.name,
            last_recovery_note="仅重建失败步骤之后的计划",
        )

    def _completed_prefix_steps(self, task: TaskRecord) -> list:
        prefix = []
        for step in task.steps:
            if step.status in {StepStatus.DONE, StepStatus.SKIPPED}:
                prefix.append(step)
                continue
            break
        return prefix

    def _finalize_failed_execution(self, task: TaskRecord, resolution: FailureResolution) -> None:
        if task.status not in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            transition_task(task, TaskStatus.FAILED)
        self._update_checkpoint(
            task,
            phase="FAILED",
            stage="failed_execution",
            resumable=resolution != FailureResolution.FAIL_FAST,
            resume_reason=resolution.value.lower(),
            context_version=task.context_layers.version,
        )
        self._append_progress(
            task,
            "failed",
            "任务执行失败。",
            f"失败类型：{task.failure_category.value}；恢复策略：{resolution.value}；错误信息：{task.failure_message or '无'}",
        )

    def _finalize_task(self, task: TaskRecord, request: TaskCreateRequest) -> None:
        self._build_result_citations(task)
        self._write_long_term_memory(task, request.memory_scope)
        self._extract_and_store_profile(task, request)
        self._append_session_message(
            task.session_id,
            ChatMessageRole.ASSISTANT,
            task.result or task.failure_message or "任务已完成，但没有可展示的结果。",
            task_id=task.id,
        )
        self.session_store.compress_session_context(task.session_id)
        self._touch_session(task.session_id, task)
        self.repository.save(task)
        log_event("task.completed", task_id=task.id, status=task.status.value, steps=len(task.steps))

    def _build_result_citations(self, task: TaskRecord) -> None:
        citation_map = self._build_citation_map(task)
        task.citation_sources = citation_map.sources
        task.paragraph_citations = citation_map.paragraphs

    def _build_citation_map(self, task: TaskRecord) -> CitationMap:
        """Build a CitationMap containing all citation sources and paragraph mappings."""
        cmap = CitationMap()

        for memory in task.recalled_memories:
            detail_segments = [
                f"类型：{memory.memory_type}",
                f"作用域：{memory.scope}",
                f"主题：{memory.topic}",
                f"摘要：{memory.summary}",
            ]
            if memory.retrieval_score is not None:
                detail_segments.append(f"召回分数：{memory.retrieval_score:.2f}")
            if memory.retrieval_reason:
                detail_segments.append(f"命中原因：{memory.retrieval_reason}")
            if memory.retrieval_channels:
                detail_segments.append(f"检索通道：{', '.join(memory.retrieval_channels)}")
            if memory.source.session_id:
                detail_segments.append(f"来源会话：{memory.source.session_id}")
            if memory.source.task_id:
                detail_segments.append(f"来源任务：{memory.source.task_id}")
            cmap.add_source(
                kind="memory",
                label=f"记忆：{memory.topic}",
                detail=" | ".join(detail_segments),
                source_record_id=memory.id,
                source_session_id=memory.source.session_id,
                source_task_id=memory.source.task_id,
                excerpt=memory.details[:240],
            )

        for fact in task.profile_hits:
            detail_segments = [
                f"标签：{fact.label}",
                f"值：{fact.value}",
                f"置信度：{fact.confidence:.2f}",
            ]
            if fact.summary:
                detail_segments.append(f"说明：{fact.summary}")
            if fact.source_session_id:
                detail_segments.append(f"来源会话：{fact.source_session_id}")
            if fact.source_task_id:
                detail_segments.append(f"来源任务：{fact.source_task_id}")
            cmap.add_source(
                kind="profile",
                label=f"画像：{fact.label}={fact.value}",
                detail=" | ".join(detail_segments),
                source_record_id=fact.id,
                source_session_id=fact.source_session_id,
                source_task_id=fact.source_task_id,
                excerpt=(fact.summary or f"{fact.label}: {fact.value}")[:240],
            )

        for index, message in enumerate(task.context_layers.recent_messages[:4], start=1):
            cmap.add_source(
                kind="session_message",
                label=f"会话消息 {index}",
                detail=message[:240],
                source_session_id=task.session_id,
                source_task_id=task.id,
                excerpt=message[:240],
            )

        if task.context_layers.source_summary:
            cmap.add_source(
                kind="source_summary",
                label="外部材料摘要",
                detail=task.context_layers.source_summary[:240],
                source_session_id=task.session_id,
                source_task_id=task.id,
                excerpt=task.context_layers.source_summary[:240],
            )

        # Build paragraph citations using the accumulated sources
        if task.result:
            self._build_paragraph_citations_into_map(task.result or "", cmap)

        return cmap

    def _build_citation_source_pool(self, task: TaskRecord) -> list[CitationSource]:
        """Deprecated: use _build_citation_map instead. Returns list for backward compatibility."""
        return self._build_citation_map(task).sources

    def _build_paragraph_citations(self, result_markdown: str, sources: list[CitationSource]) -> list[ParagraphCitation]:
        """Deprecated: use _build_paragraph_citations_into_map instead."""
        if not result_markdown.strip() or not sources:
            return []
        cmap = CitationMap()
        for source in sources:
            cmap.add_source(kind=source.kind, label=source.label, detail=source.detail,
                           source_record_id=source.source_record_id,
                           source_session_id=source.source_session_id,
                           source_task_id=source.source_task_id, excerpt=source.excerpt)
        self._build_paragraph_citations_into_map(result_markdown, cmap)
        return cmap.paragraphs

    def _build_paragraph_citations_into_map(self, result_markdown: str, cmap: CitationMap) -> None:
        """Populate paragraph citations into an existing CitationMap using source scoring."""
        if not result_markdown.strip() or not cmap.sources:
            return

        body = self._extract_primary_result_body(result_markdown)
        paragraphs = self._extract_citation_paragraphs(body)

        for index, paragraph in enumerate(paragraphs):
            scored = []
            paragraph_tokens = self._tokenize_for_citations(paragraph)
            normalized = paragraph.lower()
            for source in cmap.sources:
                source_tokens = self._tokenize_for_citations(
                    " ".join(filter(None, [source.label, source.detail, source.excerpt or ""]))
                )
                score = self._score_citation_source(paragraph_tokens, normalized, source)
                if score > 0:
                    scored.append((score, source))
            scored.sort(key=lambda item: item[0], reverse=True)
            matched_sources = [item[1] for item in scored[:2]]
            if not matched_sources:
                continue
            cmap.add_paragraph(
                paragraph_index=index,
                paragraph_text=paragraph[:400],
                source_ids=[item.id for item in matched_sources],
                source_labels=[item.label for item in matched_sources],
            )

    def _extract_primary_result_body(self, result_markdown: str) -> str:
        payload = result_markdown.replace("\r\n", "\n")
        deliverable_markers = ["## 回答正文", "## Deliverable"]
        tool_markers = ["\n## 工具调用", "\n## Tool Invocations"]
        for marker in deliverable_markers:
            if marker in payload:
                payload = payload.split(marker, 1)[1]
                break
        for marker in tool_markers:
            if marker in payload:
                payload = payload.split(marker, 1)[0]
                break
        return payload.strip()

    def _extract_citation_paragraphs(self, body: str) -> list[str]:
        chunks = [item.strip() for item in re.split(r"\n{2,}", body) if item.strip()]
        paragraphs: list[str] = []
        for chunk in chunks:
            if chunk.startswith("```"):
                continue
            if chunk.startswith("|") and chunk.endswith("|"):
                continue
            cleaned = re.sub(r"^#{1,6}\s+", "", chunk.strip())
            cleaned = re.sub(r"^[-*]\s+", "", cleaned)
            cleaned = re.sub(r"^\d+\.\s+", "", cleaned)
            if len(cleaned) < 12:
                continue
            paragraphs.append(cleaned)
        return paragraphs

    def _tokenize_for_citations(self, text: str) -> set[str]:
        normalized = re.sub(r"[`#*_\-\n\r:：，。,.()/|]+", " ", text.lower())
        tokens = {item.strip() for item in normalized.split() if len(item.strip()) >= 2}
        chinese_segments = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
        for segment in chinese_segments:
            for index in range(len(segment) - 1):
                tokens.add(segment[index : index + 2])
            if len(segment) >= 4:
                for index in range(len(segment) - 3):
                    tokens.add(segment[index : index + 4])
        return tokens

    def _score_citation_source(self, paragraph_tokens: set[str], normalized_paragraph: str, source: CitationSource) -> int:
        source_tokens = self._tokenize_for_citations(" ".join(filter(None, [source.label, source.detail, source.excerpt or ""])))
        score = 0
        for token in source_tokens:
            if token in normalized_paragraph:
                score += 3 if len(token) >= 6 else 2
            elif token in paragraph_tokens:
                score += 1
        if source.kind == "profile" and any(
            keyword in normalized_paragraph
            for keyword in ("偏好", "最想学", "想学", "喜欢", "语言", "学习方向", "技术栈")
        ):
            score += 8
        return score

    def _record_progress(self, task_id: str, stage: str, message: str, detail: str | None = None) -> None:
        task = self.repository.get(task_id)
        if task is None:
            return
        self._append_progress(task, stage, message, detail)
        task.checkpoint.current_stage = stage
        task.checkpoint.last_saved_at = task.updated_at
        self.repository.save(task)

    def _record_live_result(self, task_id: str, text: str) -> None:
        task = self.repository.get(task_id)
        if task is None:
            return
        task.live_result = text
        task.checkpoint.last_saved_at = task.updated_at
        self.repository.save(task)

    def _append_progress(self, task: TaskRecord, stage: str, message: str, detail: str | None = None) -> None:
        task.progress_updates.append(ProgressUpdate(stage=stage, message=message, detail=detail))
    def _write_long_term_memory(self, task: TaskRecord, scope: str) -> None:
        if not task.result:
            return
        system_prompt, user_prompt = self.prompts.memory_summary_messages(task.title, task.result)
        payload = self.llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        topic = payload.get("topic", task.title[:100])
        summary = payload.get("summary", "Completed a task.")
        details = payload.get("details", task.result[:1200])
        tags = [str(item) for item in payload.get("tags", [])]
        record = LongTermMemoryRecord(
            scope=scope,
            memory_type=self._infer_memory_type(task, payload),
            topic=topic,
            summary=summary,
            details=details,
            tags=tags,
            embedding=[],
            source=MemorySource(task_id=task.id, session_id=task.session_id, source_type="task_result"),
            versions=[
                MemoryVersion(
                    version=1,
                    topic=topic,
                    summary=summary,
                    details=details,
                    tags=tags,
                    updated_by="system",
                )
            ],
        )
        self.long_term_memory.remember(record)

    def _infer_memory_type(self, task: TaskRecord, payload: dict[str, object]) -> str:
        topic = str(payload.get("topic", task.title)).lower()
        summary = str(payload.get("summary", "")).lower()
        combined = f"{task.title} {topic} {summary}".lower()
        if any(keyword in combined for keyword in ["偏好", "喜欢", "想学", "最想学", "语言"]):
            return "preference"
        if any(keyword in combined for keyword in ["文档", "资料", "文件", "摘要", "总结"]) or any(
            step.tool_name == "read_local_file" for step in task.steps
        ):
            return "document_note"
        if task.session_id and len(task.context_layers.recent_messages) >= 4:
            return "conversation_summary"
        if any(keyword in combined for keyword in ["事实", "规则", "定义", "信息"]):
            return "fact"
        return "task_result"

    def _format_recalled_memory_context(self, item: LongTermMemoryRecord) -> str:
        segments = [f"{item.topic}: {item.summary}", f"type={item.memory_type}"]
        if item.retrieval_score is not None:
            segments.append(f"score={item.retrieval_score:.2f}")
        if item.retrieval_reason:
            segments.append(f"reason={item.retrieval_reason}")
        return " | ".join(segments)

    def _append_session_message(
        self,
        session_id: str | None,
        role: ChatMessageRole,
        content: str,
        *,
        task_id: str | None = None,
        session_title_hint: str | None = None,
    ) -> ChatMessage | None:
        return self.session_store.append_message(
            session_id, role, content, task_id=task_id, session_title_hint=session_title_hint
        )

    def _touch_session(self, session_id: str | None, task: TaskRecord) -> None:
        self.session_store.touch_session(
            session_id,
            last_task_id=task.id,
            task_title=task.title,
            profile_hits=task.profile_hits,
        )

    def _extract_and_store_profile(self, task: TaskRecord, request: TaskCreateRequest) -> None:
        source_message = next((entry for entry in reversed(task.memory) if entry.kind == "user_goal"), None)
        extracted = self.profile_manager.extract_facts(
            request.goal,
            session_id=task.session_id,
            message_id=source_message.id if source_message else None,
            task_id=task.id,
        )
        for fact in extracted:
            self.profile_manager.remember(fact)

    def _build_context_layers(self, request: TaskCreateRequest) -> ContextLayer:
        return self.context_builder.build(request)

    def _build_session_context(self, session_id: str | None) -> dict[str, object]:
        return self.context_builder._build_session_context(session_id)

    def _render_context_layers(self, context_layers: ContextLayer) -> str:
        parts: list[str] = []
        if context_layers.system_instructions:
            parts.append(f"System instructions:\n{context_layers.system_instructions}")
        if context_layers.session_summary:
            parts.append(f"Session summary:\n{context_layers.session_summary}")
        if context_layers.recent_messages:
            parts.append("Recent messages:\n" + "\n".join(f"- {item}" for item in context_layers.recent_messages))
        if context_layers.condensed_recent_messages:
            parts.append("Condensed recent messages:\n" + "\n".join(f"- {item}" for item in context_layers.condensed_recent_messages))
        if context_layers.recalled_memories:
            parts.append("Recalled memories:\n" + "\n".join(f"- {item}" for item in context_layers.recalled_memories))
        if context_layers.profile_facts:
            parts.append("User profile facts:\n" + "\n".join(f"- {item}" for item in context_layers.profile_facts))
        if context_layers.working_memory:
            parts.append("Working memory:\n" + "\n".join(f"- {item}" for item in context_layers.working_memory))
        if context_layers.source_summary:
            parts.append(f"Source summary:\n{context_layers.source_summary}")
        if context_layers.build_notes:
            parts.append("Context build notes:\n" + "\n".join(f"- {item}" for item in context_layers.build_notes))
        if context_layers.trace_entries:
            lines = [
                f"[{e.layer}] {e.source}: {e.message}"
                for e in context_layers.trace_entries
            ]
            parts.append("Context trace:\n" + "\n".join(f"- {line}" for line in lines))
        if context_layers.budget_usage:
            bu = context_layers.budget_usage
            parts.append(
                f"Context budget: session_summary={bu.session_summary_used}/{bu.session_summary_limit}, "
                f"recent_msg={bu.recent_messages_count}/{bu.recent_messages_limit}, "
                f"profile_facts={bu.profile_facts_count}/{bu.profile_facts_limit}, "
                f"working_mem={bu.working_memory_count}/{bu.working_memory_limit}"
            )
        return "\n\n".join(parts).strip()

    def _restore_request(self, task: TaskRecord | None) -> TaskCreateRequest | None:
        if task is None:
            return None
        original = task.metadata.get("original_request")
        if not isinstance(original, dict):
            return None
        return TaskCreateRequest.model_validate(original)

    def _mark_task_for_replan(
        self,
        task: TaskRecord,
        *,
        reason: ReplanReason,
        summary: str,
        detail: str | None,
        failure_category: FailureCategory = FailureCategory.NONE,
        resume_from_step_id: str | None = None,
        resume_from_step_name: str | None = None,
    ) -> None:
        transition_task(task, TaskStatus.REPLANNING)
        task.replan_count += 1
        task.last_replan_reason = reason
        task.replan_history.append(
            ReplanEvent(
                reason=reason,
                summary=summary,
                detail=detail,
                failure_category=failure_category,
                trigger_phase=task.checkpoint.phase,
                checkpoint_stage=task.checkpoint.current_stage,
                checkpoint_step_id=task.checkpoint.current_step_id,
                resume_from_step_id=resume_from_step_id,
                resume_from_step_name=resume_from_step_name,
                recovery_strategy="revise_current_result" if reason == ReplanReason.REVIEW_FEEDBACK else "rebuild_plan_or_retry",
                recovery_attempts=task.checkpoint.recovery_attempt,
            )
        )
        self._update_checkpoint(
            task,
            phase="REPLANNING",
            stage="replanning",
            current_step_id=task.checkpoint.current_step_id,
            resumable=True,
            resume_reason=reason.value,
            context_version=task.context_layers.version,
        )
        self._append_progress(task, "replanning", summary, detail)

    def _update_checkpoint(
        self,
        task: TaskRecord,
        *,
        phase: str,
        stage: str,
        current_step_id: str | None = None,
        resumable: bool,
        resume_reason: str | None = None,
        context_version: int | None = None,
        last_completed_step_id: str | None = None,
        last_completed_step_name: str | None = None,
        last_failure_category: FailureCategory | None = None,
        last_failure_resolution: FailureResolution | None = None,
        failure_count: int | None = None,
        recovery_attempt: int | None = None,
        last_recovery_step_id: str | None = None,
        last_recovery_step_name: str | None = None,
        last_recovery_note: str | None = None,
    ) -> None:
        task.checkpoint.phase = TaskPhase[phase]
        task.checkpoint.current_stage = stage
        task.checkpoint.current_step_id = current_step_id
        task.checkpoint.resumable = resumable
        task.checkpoint.resume_reason = resume_reason
        if context_version is not None:
            task.checkpoint.context_version = context_version
        if last_completed_step_id is not None:
            task.checkpoint.last_completed_step_id = last_completed_step_id
        if last_completed_step_name is not None:
            task.checkpoint.last_completed_step_name = last_completed_step_name
        if last_failure_category is not None:
            task.checkpoint.last_failure_category = last_failure_category
        if last_failure_resolution is not None:
            task.checkpoint.last_failure_resolution = last_failure_resolution
        if failure_count is not None:
            task.checkpoint.failure_count = failure_count
        if recovery_attempt is not None:
            task.checkpoint.recovery_attempt = recovery_attempt
        if last_recovery_step_id is not None:
            task.checkpoint.last_recovery_step_id = last_recovery_step_id
        if last_recovery_step_name is not None:
            task.checkpoint.last_recovery_step_name = last_recovery_step_name
        if last_recovery_note is not None:
            task.checkpoint.last_recovery_note = last_recovery_note
        task.checkpoint.last_saved_at = utcnow()

    def _trim_text(self, text: str, limit: int) -> str:
        value = (text or "").strip()
        if len(value) <= limit:
            return value
        return value[: max(limit - 1, 0)] + "…"

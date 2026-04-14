from __future__ import annotations

import threading
import time

from orion_agent.core.config import Settings, get_settings
from orion_agent.core.embedding_runtime import build_embedder
from orion_agent.core.evaluation import EvaluationResult, TaskEvaluator
from orion_agent.core.execution_engine import ExecutionEngine
from orion_agent.core.llm_runtime import BaseLLMClient, build_llm_client
from orion_agent.core.memory import LongTermMemoryManager, TaskMemoryManager
from orion_agent.core.models import (
    FailureCategory,
    LongTermMemoryRecord,
    ParsedGoal,
    ProgressUpdate,
    TaskCreateRequest,
    TaskRecord,
    TaskResponse,
    TaskStatus,
)
from orion_agent.core.observability import Timer, log_event
from orion_agent.core.planner import Planner
from orion_agent.core.prompts import PromptLibrary
from orion_agent.core.reflection import Reflector
from orion_agent.core.repository import TaskRepository
from orion_agent.core.state_machine import transition_task
from orion_agent.core.tools import ToolRegistry
from orion_agent.core.vector_store import build_vector_store


class AgentService:
    """Orchestrates parsing, planning, execution, memory, and review."""

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
        self._active_runs: dict[str, threading.Thread] = {}
        self._runs_lock = threading.RLock()

    def create_and_run_task(self, request: TaskCreateRequest) -> TaskResponse:
        with Timer("task.run", goal=request.goal, memory_scope=request.memory_scope):
            task = self._create_task_record(request)
            task = self._run_task_flow(task.id, request)
            return TaskResponse.from_record(task)

    def create_task_async(self, request: TaskCreateRequest) -> TaskResponse:
        task = self._create_task_record(request)
        worker = threading.Thread(
            target=self._run_task_in_background,
            args=(task.id, request),
            daemon=True,
            name=f"task-worker-{task.id}",
        )
        with self._runs_lock:
            self._active_runs[task.id] = worker
        worker.start()
        return TaskResponse.from_record(task)

    def get_task(self, task_id: str) -> TaskResponse | None:
        task = self.repository.get(task_id)
        if task is None:
            return None
        return TaskResponse.from_record(task)

    def list_tasks(self, limit: int = 20) -> list[TaskResponse]:
        return [TaskResponse.from_record(task) for task in self.repository.list(limit=limit)]

    def stream_task_events(self, task_id: str, poll_interval: float = 0.18):
        last_signature: tuple[str, str, int, int, str, str] | None = None
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
            )
            if signature != last_signature:
                last_signature = signature
                event_name = "completed" if task.status in {
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                } else "task_update"
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
            self.repository.save(task)
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
        has_key = bool(
            self.settings.minimax_api_key if provider == "minimax" else self.settings.openai_api_key
        )
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
        if not configured:
            payload["status"] = "missing_credentials"
            return payload
        if perform_request:
            payload.update(self.llm_client.probe())
        else:
            payload["status"] = "configured"
        return payload

    def _parse_goal(self, request: TaskCreateRequest) -> ParsedGoal:
        system_prompt, user_prompt = self.prompts.parse_goal_messages(request.model_dump_json(indent=2))
        payload = self.llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        return ParsedGoal.model_validate(payload)

    def _create_task_record(self, request: TaskCreateRequest) -> TaskRecord:
        task = TaskRecord(title=request.goal, metadata=request.metadata)
        self._append_progress(task, "queued", "任务已创建，准备开始执行。", request.goal)
        self.repository.save(task)
        log_event("task.created", task_id=task.id, goal=request.goal)
        return task

    def _run_task_in_background(self, task_id: str, request: TaskCreateRequest) -> None:
        try:
            self._run_task_flow(task_id, request)
        finally:
            with self._runs_lock:
                self._active_runs.pop(task_id, None)

    def _run_task_flow(self, task_id: str, request: TaskCreateRequest) -> TaskRecord:
        task = self.repository.get(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")

        self._append_progress(task, "thinking", "正在读取输入任务。")
        self._append_progress(task, "thinking", "正在解析输入内容。", "提取目标、约束、输出格式和领域标签。")
        self.repository.save(task)

        task.parsed_goal = self._parse_goal(request)
        self.memory_manager.write(task, "user_goal", request.goal)
        transition_task(task, TaskStatus.PARSED)
        self._append_progress(task, "thinking", "正在整理约束。", "已完成目标解析，开始归纳约束条件和期望输出。")
        self._append_progress(task, "thinking", "正在确认任务重点。", task.parsed_goal.goal)
        self.repository.save(task)

        self._append_progress(task, "memory", "正在检索记忆。", f"记忆作用域：{request.memory_scope}")
        self.repository.save(task)

        task.recalled_memories = self.long_term_memory.recall(
            query=request.goal,
            scope=request.memory_scope,
            limit=5,
        )
        self.memory_manager.write(task, "memory_scope", request.memory_scope)
        self._append_progress(
            task,
            "memory",
            "已完成记忆检索。",
            f"召回到 {len(task.recalled_memories)} 条相关记忆。",
        )
        self.repository.save(task)

        self._append_progress(
            task,
            "planning",
            "正在生成执行计划。",
            "开始组合步骤顺序、工具使用和结果产出方式。",
        )
        self.repository.save(task)

        task.steps = self.planner.build_plan(
            parsed_goal=task.parsed_goal,
            recalled_memories=task.recalled_memories,
            source_available=bool(request.source_text or request.source_path),
            enable_web_search=request.enable_web_search,
        )
        transition_task(task, TaskStatus.PLANNED)
        self._append_progress(task, "planning", "正在整理步骤结构。", "把任务拆成可执行步骤并绑定工具。")
        self._append_progress(task, "planning", "执行计划已生成。", f"共规划了 {len(task.steps)} 个步骤。")
        self.repository.save(task)

        transition_task(task, TaskStatus.RUNNING)
        self._append_progress(task, "running", "开始执行任务。", "系统将依次推进各个步骤并持续回传进度。")
        self.repository.save(task)

        task = self.executor.run(
            task,
            task.parsed_goal,
            request,
            task.recalled_memories,
            on_progress=lambda stage, message, detail=None: self._record_progress(task.id, stage, message, detail),
            on_result_stream=lambda text: self._record_live_result(task.id, text),
            on_task_update=lambda updated_task: self.repository.save(updated_task),
        )
        task.live_result = task.result
        self.repository.save(task)

        transition_task(task, TaskStatus.REFLECTING)
        self._append_progress(task, "review", "正在复核结果质量。", "检查覆盖度、结构完整性与可执行性。")
        self.repository.save(task)

        task.review = self.reflector.review(task, task.parsed_goal)
        if task.review.passed:
            transition_task(task, TaskStatus.COMPLETED)
            self._append_progress(task, "completed", "任务执行完成。", task.review.summary)
        elif task.replan_count < self.settings.replan_limit:
            transition_task(task, TaskStatus.REPLANNING)
            self._append_progress(task, "replanning", "评审未通过，正在重规划并修订回答。", task.review.summary)
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
            task.replan_count += 1
            task.live_result = task.result
            transition_task(task, TaskStatus.REFLECTING)
            self._append_progress(task, "review", "正在复核修订后的结果。", "系统已根据评审意见完成一次重规划。")
            self.repository.save(task)

            task.review = self.reflector.review(task, task.parsed_goal)
            if task.review.passed:
                transition_task(task, TaskStatus.COMPLETED)
                self._append_progress(task, "completed", "任务执行完成。", task.review.summary)
            else:
                task.failure_category = FailureCategory.REVIEW_FAILED
                task.failure_message = task.review.summary
                transition_task(task, TaskStatus.FAILED)
                self._append_progress(task, "failed", "评审未通过，已达到当前重规划上限。", task.review.summary)
        else:
            task.failure_category = FailureCategory.REVIEW_FAILED
            task.failure_message = task.review.summary
            transition_task(task, TaskStatus.FAILED)
            self._append_progress(task, "failed", "任务执行失败。", task.review.summary if task.review else None)

        self._write_long_term_memory(task, request.memory_scope)
        self.repository.save(task)
        log_event("task.completed", task_id=task.id, status=task.status.value, steps=len(task.steps))
        return task

    def _record_progress(self, task_id: str, stage: str, message: str, detail: str | None = None) -> None:
        task = self.repository.get(task_id)
        if task is None:
            return
        self._append_progress(task, stage, message, detail)
        self.repository.save(task)

    def _record_live_result(self, task_id: str, text: str) -> None:
        task = self.repository.get(task_id)
        if task is None:
            return
        task.live_result = text
        self.repository.save(task)

    def _append_progress(self, task: TaskRecord, stage: str, message: str, detail: str | None = None) -> None:
        task.progress_updates.append(ProgressUpdate(stage=stage, message=message, detail=detail))

    def _write_long_term_memory(self, task: TaskRecord, scope: str) -> None:
        if not task.result:
            return
        system_prompt, user_prompt = self.prompts.memory_summary_messages(task.title, task.result)
        payload = self.llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        record = LongTermMemoryRecord(
            scope=scope,
            topic=payload.get("topic", task.title[:100]),
            summary=payload.get("summary", "Completed a task."),
            details=payload.get("details", task.result[:1200]),
            tags=[str(item) for item in payload.get("tags", [])],
            embedding=[],
        )
        self.long_term_memory.remember(record)

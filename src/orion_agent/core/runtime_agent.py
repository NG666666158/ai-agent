from __future__ import annotations

from orion_agent.core.config import Settings, get_settings
from orion_agent.core.evaluation import EvaluationResult, TaskEvaluator
from orion_agent.core.embedding_runtime import build_embedder
from orion_agent.core.execution_engine import ExecutionEngine
from orion_agent.core.llm_runtime import BaseLLMClient, build_llm_client
from orion_agent.core.memory import LongTermMemoryManager, TaskMemoryManager
from orion_agent.core.models import (
    LongTermMemoryRecord,
    ParsedGoal,
    TaskCreateRequest,
    TaskRecord,
    TaskResponse,
    TaskStatus,
)
from orion_agent.core.planner import Planner
from orion_agent.core.prompts import PromptLibrary
from orion_agent.core.observability import Timer, log_event
from orion_agent.core.reflection import Reflector
from orion_agent.core.repository import TaskRepository
from orion_agent.core.state_machine import transition_task
from orion_agent.core.tools import ToolRegistry
from orion_agent.core.vector_store import build_vector_store


class AgentService:
    """Orchestrates parsing, planning, execution, long-term memory, and review."""

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
        self.executor = ExecutionEngine(self.tool_registry, self.memory_manager, self.llm_client, self.prompts)
        self.reflector = Reflector(self.llm_client, self.prompts)
        self.evaluator = TaskEvaluator()

    def create_and_run_task(self, request: TaskCreateRequest) -> TaskResponse:
        with Timer("task.run", goal=request.goal, memory_scope=request.memory_scope):
            task = TaskRecord(title=request.goal, metadata=request.metadata)
            self.repository.save(task)
            log_event("task.created", task_id=task.id, goal=request.goal)

            task.parsed_goal = self._parse_goal(request)
            self.memory_manager.write(task, "user_goal", request.goal)
            transition_task(task, TaskStatus.PARSED)
            self.repository.save(task)

            task.recalled_memories = self.long_term_memory.recall(
                query=request.goal,
                scope=request.memory_scope,
                limit=5,
            )
            self.memory_manager.write(task, "memory_scope", request.memory_scope)

            task.steps = self.planner.build_plan(
                parsed_goal=task.parsed_goal,
                recalled_memories=task.recalled_memories,
                source_available=bool(request.source_text or request.source_path),
                enable_web_search=request.enable_web_search,
            )
            transition_task(task, TaskStatus.PLANNED)
            self.repository.save(task)

            transition_task(task, TaskStatus.RUNNING)
            task = self.executor.run(task, task.parsed_goal, request, task.recalled_memories)
            self.repository.save(task)

            transition_task(task, TaskStatus.REFLECTING)
            task.review = self.reflector.review(task, task.parsed_goal)
            transition_task(task, TaskStatus.COMPLETED if task.review.passed else TaskStatus.FAILED)

            self._write_long_term_memory(task, request.memory_scope)
            self.repository.save(task)
            log_event("task.completed", task_id=task.id, status=task.status.value, steps=len(task.steps))
            return TaskResponse.from_record(task)

    def get_task(self, task_id: str) -> TaskResponse | None:
        task = self.repository.get(task_id)
        if task is None:
            return None
        return TaskResponse.from_record(task)

    def list_tasks(self, limit: int = 20) -> list[TaskResponse]:
        return [TaskResponse.from_record(task) for task in self.repository.list(limit=limit)]

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
        return {
            "task_count": self.repository.count_tasks(),
            "memory_count": self.repository.count_long_term_memories(),
            "vector_backend": self.vector_store.health()["backend"],
            "vector_status": self.vector_store.health()["status"],
        }

    def _parse_goal(self, request: TaskCreateRequest) -> ParsedGoal:
        system_prompt, user_prompt = self.prompts.parse_goal_messages(request.model_dump_json(indent=2))
        payload = self.llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        return ParsedGoal.model_validate(payload)

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

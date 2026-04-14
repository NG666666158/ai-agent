from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

from orion_agent.core.llm_runtime import BaseLLMClient, FallbackLLMClient
from orion_agent.core.models import TaskCreateRequest, TaskResponse, TaskStatus
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService


ToolOverride = dict[str, Callable[..., str]]


@dataclass
class PipelineFixture:
    service: AgentService

    @classmethod
    def build(cls, llm_client: BaseLLMClient | None = None) -> "PipelineFixture":
        service = AgentService(
            repository=TaskRepository(db_path=":memory:"),
            llm_client=llm_client or FallbackLLMClient(),
        )
        return cls(service=service)

    def run_request(self, **kwargs) -> TaskResponse:
        request = TaskCreateRequest(**kwargs)
        return self.service.create_and_run_task(request)

    def assert_completed(self, response: TaskResponse) -> None:
        assert response.status == TaskStatus.COMPLETED
        assert response.result is not None

    def assert_tool_sequence_contains(self, response: TaskResponse, expected_tools: list[str]) -> None:
        called = [item.tool_name for item in response.tool_invocations]
        for tool_name in expected_tools:
            assert tool_name in called, f"expected tool {tool_name!r} in {called!r}"

    def assert_result_contains_keywords(self, response: TaskResponse, keywords: list[str]) -> None:
        payload = response.result or ""
        for keyword in keywords:
            assert keyword in payload, f"expected keyword {keyword!r} in result"

    @contextmanager
    def tool_overrides(self, overrides: ToolOverride):
        registry = self.service.tool_registry
        original = dict(registry._handlers)
        registry._handlers.update(overrides)
        try:
            yield
        finally:
            registry._handlers = original

    def close(self) -> None:
        self.service.repository.close()

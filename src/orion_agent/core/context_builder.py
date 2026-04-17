"""Dedicated context layer builder for Orion Agent.

Extracts context assembly from AgentService so that context layers,
budgets, and traceability can evolve independently.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from orion_agent.core.models import ContextLayer, TaskCreateRequest

if TYPE_CHECKING:
    from orion_agent.core.profile import UserProfileManager
    from orion_agent.core.repository import TaskRepository

CONTEXT_BUDGET = {
    "session_summary": 1_200,
    "recent_messages": 6,
    "condensed_recent_messages": 3,
    "recalled_memories": 5,
    "profile_facts": 6,
    "working_memory": 8,
    "source_summary": 600,
}


class ContextBuilder:
    """Builds context layers from task requests and session state."""

    def __init__(self, profile_manager: UserProfileManager, repository: TaskRepository) -> None:
        self._profile_manager = profile_manager
        self._repository = repository

    def build(self, request: TaskCreateRequest) -> ContextLayer:
        """Build a complete ContextLayer from a task creation request."""
        session_context = self._build_session_context(request.session_id)
        budget = dict(CONTEXT_BUDGET)

        source_summary = self._trim_text(request.source_text or "", budget["source_summary"])
        recent_messages = [
            self._trim_text(item, 240)
            for item in list(session_context["recent_messages"])[: budget["recent_messages"]]
        ]
        condensed_recent_messages = [
            self._trim_text(item, 120) for item in recent_messages[: budget["condensed_recent_messages"]]
        ]
        profile_facts = [
            self._trim_text(item, 120)
            for item in list(session_context["profile_facts"])[: budget["profile_facts"]]
        ]
        build_notes = [
            f"session_summary<{budget['session_summary']} chars",
            f"recent_messages<={budget['recent_messages']}",
            f"profile_facts<={budget['profile_facts']}",
            f"source_summary<{budget['source_summary']} chars",
        ]

        return ContextLayer(
            system_instructions="Follow the task goal, satisfy constraints, and keep the output structured.",
            session_summary=self._trim_text(str(session_context["session_summary"]), budget["session_summary"]),
            recent_messages=recent_messages,
            condensed_recent_messages=condensed_recent_messages,
            profile_facts=profile_facts,
            working_memory=[
                f"goal={request.goal}",
                f"expected_output={request.expected_output}",
                f"memory_scope={request.memory_scope}",
            ][: budget["working_memory"]],
            source_summary=source_summary,
            layer_budget=budget,
            build_notes=build_notes,
            version=int(time.time()),
        )

    def _build_session_context(self, session_id: str | None) -> dict[str, object]:
        """Build session context from session ID or fall back to defaults."""
        if not session_id:
            return {
                "session_summary": "",
                "recent_messages": [],
                "profile_facts": self._profile_manager.snapshot(limit=6),
            }
        session = self._repository.get_session(session_id)
        if session is None:
            return {
                "session_summary": "",
                "recent_messages": [],
                "profile_facts": self._profile_manager.snapshot(limit=6),
            }
        messages = self._repository.list_session_messages(session_id, limit=12)
        recent_messages = [f"{item.role.value}: {item.content[:240]}" for item in messages[-6:]]
        profile_facts = session.profile_snapshot or self._profile_manager.snapshot(limit=6)
        return {
            "session_summary": session.context_summary.strip(),
            "recent_messages": recent_messages,
            "profile_facts": profile_facts,
        }

    @staticmethod
    def _trim_text(text: str, limit: int) -> str:
        """Trim text to the given limit, adding ellipsis if truncated."""
        value = (text or "").strip()
        if len(value) <= limit:
            return value
        return value[: max(limit - 1, 0)] + "…"
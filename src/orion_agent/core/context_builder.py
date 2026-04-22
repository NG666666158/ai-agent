"""Dedicated context layer builder for Orion Agent.

Extracts context assembly from AgentService so that context layers,
budgets, and traceability can evolve independently.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from orion_agent.core.models import (
    ContextBudgetUsage,
    ContextLayer,
    ContextTraceEntry,
    TaskCreateRequest,
    TrimReason,
    utcnow,
)

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
        trace_entries: list[ContextTraceEntry] = []
        now = utcnow()

        # session_summary
        original_summary = str(session_context["session_summary"])
        session_summary_trim_reason = TrimReason.TRUNCATED if len(original_summary) > budget["session_summary"] else TrimReason.NONE
        session_summary_text = self._trim_text(original_summary, budget["session_summary"])
        trace_entries.append(
            ContextTraceEntry(
                layer="session_summary",
                source="session",
                source_id=request.session_id,
                message=f"limit={budget['session_summary']} chars, used={len(session_summary_text)}, reason={session_summary_trim_reason.value}",
            )
        )

        # recent_messages
        raw_recent = list(session_context["recent_messages"])
        if len(raw_recent) > budget["recent_messages"]:
            recent_messages_trim_reason = TrimReason.FILTERED
        elif any(len(m) > 240 for m in raw_recent):
            recent_messages_trim_reason = TrimReason.TRUNCATED
        else:
            recent_messages_trim_reason = TrimReason.NONE
        recent_messages = [self._trim_text(item, 240) for item in raw_recent[: budget["recent_messages"]]]
        trace_entries.append(
            ContextTraceEntry(
                layer="recent_messages",
                source="session_messages",
                source_id=request.session_id,
                message=f"limit={budget['recent_messages']}, count={len(recent_messages)}, reason={recent_messages_trim_reason.value}",
            )
        )

        # condensed_recent_messages (compression step)
        condensed_recent_messages_trim_reason = TrimReason.COMPRESSED if len(recent_messages) > budget["condensed_recent_messages"] else TrimReason.NONE
        condensed_recent_messages = [self._trim_text(item, 120) for item in recent_messages[: budget["condensed_recent_messages"]]]
        trace_entries.append(
            ContextTraceEntry(
                layer="condensed_recent_messages",
                source="session_messages",
                source_id=request.session_id,
                message=f"limit={budget['condensed_recent_messages']}, count={len(condensed_recent_messages)}, reason={condensed_recent_messages_trim_reason.value}",
            )
        )

        # profile_facts
        raw_profile = list(session_context["profile_facts"])
        profile_facts_trim_reason = TrimReason.TRUNCATED if len(raw_profile) > budget["profile_facts"] else TrimReason.NONE
        profile_facts = [self._trim_text(item, 120) for item in raw_profile[: budget["profile_facts"]]]
        trace_entries.append(
            ContextTraceEntry(
                layer="profile_facts",
                source="user_profile",
                source_id=None,
                message=f"limit={budget['profile_facts']}, count={len(profile_facts)}, reason={profile_facts_trim_reason.value}",
            )
        )

        # working_memory (filter discardable entries from task memory)
        # Non-discardable entries come from the task's memory list;
        # initial entries from the request itself are never discardable.
        working_raw = [
            f"goal={request.goal}",
            f"expected_output={request.expected_output}",
            f"memory_scope={request.memory_scope}",
        ]
        # Append non-discardable entries from the task's working memory if available
        if hasattr(request, "_task_memory"):
            working_raw.extend(
                entry.content
                for entry in request._task_memory
                if not entry.discardable
            )
        working_memory = [self._trim_text(item, 240) for item in working_raw[: budget["working_memory"]]]
        trace_entries.append(
            ContextTraceEntry(
                layer="working_memory",
                source="task_request",
                source_id=None,
                message=f"limit={budget['working_memory']}, count={len(working_memory)}",
            )
        )

        # source_summary
        original_source = request.source_text or ""
        source_summary_trim_reason = TrimReason.TRUNCATED if len(original_source) > budget["source_summary"] else TrimReason.NONE
        source_summary_text = self._trim_text(original_source, budget["source_summary"])
        trace_entries.append(
            ContextTraceEntry(
                layer="source_summary",
                source="task_request",
                source_id=None,
                message=f"limit={budget['source_summary']} chars, used={len(source_summary_text)}, reason={source_summary_trim_reason.value}",
            )
        )

        # budget usage with trimming reasons
        budget_usage = ContextBudgetUsage(
            session_summary_limit=budget["session_summary"],
            session_summary_used=len(session_summary_text),
            session_summary_trim_reason=session_summary_trim_reason,
            recent_messages_limit=budget["recent_messages"],
            recent_messages_count=len(recent_messages),
            recent_messages_trim_reason=recent_messages_trim_reason,
            condensed_recent_messages_limit=budget["condensed_recent_messages"],
            condensed_recent_messages_count=len(condensed_recent_messages),
            condensed_recent_messages_trim_reason=condensed_recent_messages_trim_reason,
            recalled_memories_limit=budget["recalled_memories"],
            recalled_memories_count=0,  # filled by runtime after recall
            recalled_memories_trim_reason=TrimReason.NONE,  # set by runtime after memory recall
            profile_facts_limit=budget["profile_facts"],
            profile_facts_count=len(profile_facts),
            profile_facts_trim_reason=profile_facts_trim_reason,
            working_memory_limit=budget["working_memory"],
            working_memory_count=len(working_memory),
            working_memory_trim_reason=TrimReason.NONE,  # working_memory is constructed from request, always fits
            source_summary_limit=budget["source_summary"],
            source_summary_used=len(source_summary_text),
            source_summary_trim_reason=source_summary_trim_reason,
        )

        # legacy build_notes still produced for backward compatibility
        build_notes = [
            f"session_summary<{budget['session_summary']} chars",
            f"recent_messages<={budget['recent_messages']}",
            f"profile_facts<={budget['profile_facts']}",
            f"source_summary<{budget['source_summary']} chars",
        ]

        return ContextLayer(
            system_instructions="Follow the task goal, satisfy constraints, and keep the output structured.",
            session_summary=session_summary_text,
            recent_messages=recent_messages,
            condensed_recent_messages=condensed_recent_messages,
            profile_facts=profile_facts,
            working_memory=working_memory,
            source_summary=source_summary_text,
            layer_budget=budget,
            build_notes=build_notes,
            trace_entries=trace_entries,
            budget_usage=budget_usage,
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
        recent_messages = [f"{item.role.value}: {item.content}" for item in messages]
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

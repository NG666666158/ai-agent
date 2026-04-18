from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from orion_agent.core.models import (
    ChatMessage,
    ChatMessageRole,
    ChatSession,
    ChatSessionDetail,
    SessionCreateRequest,
    SessionSummaryRefreshRequest,
    TaskResponse,
    utcnow,
)

if TYPE_CHECKING:
    from orion_agent.core.llm_runtime import BaseLLMClient
    from orion_agent.core.profile import UserProfileManager
    from orion_agent.core.prompts import PromptLibrary
    from orion_agent.core.repository import TaskRepository


class SessionStore:
    """Boundary for session persistence and retrieval flows.

    Encapsulates session creation, message appending, summary refresh,
    branch continuation, and trace lookup so conversation governance
    is easier to evolve safely.
    """

    def __init__(
        self,
        repository: TaskRepository,
        profile_manager: UserProfileManager,
        llm_client: BaseLLMClient,
        prompts: PromptLibrary,
    ) -> None:
        self._repository = repository
        self._profile_manager = profile_manager
        self._llm_client = llm_client
        self._prompts = prompts

    def create_session(self, payload: SessionCreateRequest | None = None) -> ChatSession:
        """Create a new session, optionally branching from an existing session."""
        payload = payload or SessionCreateRequest()
        session = ChatSession(
            title=(payload.title or "新对话").strip() or "新对话",
            source_session_id=payload.source_session_id,
            profile_snapshot=self._profile_manager.snapshot(limit=6),
        )
        session = self._repository.save_session(session)
        if payload.source_session_id:
            source_detail = self.get_session(payload.source_session_id, message_limit=12, task_limit=0)
            if source_detail:
                if payload.seed_prompt:
                    self.append_message(
                        session.id,
                        ChatMessageRole.SYSTEM,
                        f"分叉续聊说明：{payload.seed_prompt}",
                    )
                for item in source_detail.messages[-6:]:
                    self.append_message(session.id, item.role, item.content, task_id=item.task_id)
                session = self._repository.get_session(session.id) or session
        return session

    def get_session(
        self, session_id: str, message_limit: int = 100, task_limit: int = 50
    ) -> ChatSessionDetail | None:
        """Retrieve a session with its messages and tasks."""
        session = self._repository.get_session(session_id)
        if session is None:
            return None
        messages = self._repository.list_session_messages(session_id, limit=message_limit)
        tasks = [
            TaskResponse.from_record(task)
            for task in self._repository.list_by_session(session_id, limit=task_limit)
        ]
        return ChatSessionDetail(session=session, messages=messages, tasks=tasks)

    def list_sessions(self, limit: int = 30) -> list[ChatSession]:
        """List recent sessions ordered by update time."""
        return self._repository.list_sessions(limit=limit)

    def list_sessions_by_source(self, source_session_id: str, limit: int = 30) -> list[ChatSession]:
        """List sessions branched from a given source session."""
        return self._repository.list_sessions_by_source(source_session_id, limit=limit)

    def refresh_session_summary(
        self, session_id: str, payload: SessionSummaryRefreshRequest | None = None
    ) -> ChatSessionDetail | None:
        """Refresh session summary via compression, then return updated session detail."""
        session = self._repository.get_session(session_id)
        if session is None:
            return None
        if payload is None or payload.force:
            self.compress_session_context(session_id, force=True)
        return self.get_session(session_id)

    def append_message(
        self,
        session_id: str,
        role: ChatMessageRole,
        content: str,
        *,
        task_id: str | None = None,
        session_title_hint: str | None = None,
    ) -> ChatMessage | None:
        """Append a message to a session, creating the session if it does not exist."""
        if not session_id or not content.strip():
            return None
        session = self._repository.get_session(session_id)
        if session is None:
            session = self._repository.save_session(
                ChatSession(id=session_id, title=(session_title_hint or "新对话")[:48])
            )
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content.strip(),
            task_id=task_id,
        )
        self._repository.save_session_message(message)
        session.message_count += 1
        if task_id:
            session.last_task_id = task_id
        self._repository.save_session(session)
        return message

    def touch_session(self, session_id: str | None, last_task_id: str, task_title: str, profile_hits: list) -> None:
        """Update session metadata after a task completes."""
        if not session_id:
            return
        session = self._repository.get_session(session_id)
        if session is None:
            return
        session.last_task_id = last_task_id
        if not session.title or session.title == "新对话":
            session.title = task_title[:48]
        if profile_hits:
            session.profile_snapshot = [f"{item.label}: {item.value}" for item in profile_hits]
        self._repository.save_session(session)

    def get_trace_lookup(self, session_id: str | None) -> dict[str, object]:
        """Return trace metadata for a session, used by context and debugging flows."""
        if not session_id:
            return {}
        session = self._repository.get_session(session_id)
        if session is None:
            return {}
        return {
            "session_id": session.id,
            "title": session.title,
            "message_count": session.message_count,
            "last_task_id": session.last_task_id,
            "source_session_id": session.source_session_id,
            "profile_snapshot_size": len(session.profile_snapshot),
            "context_summary_length": len(session.context_summary),
        }

    def compress_session_context(self, session_id: str | None, *, force: bool = False) -> None:
        """Compress older messages into a session summary."""
        if not session_id:
            return
        session = self._repository.get_session(session_id)
        if session is None:
            return
        messages = self._repository.list_session_messages(session_id, limit=200)
        if len(messages) <= 8 and not force:
            return
        older_messages = messages if force else messages[:-6]
        if not older_messages:
            return
        payload = "\n".join(f"- {item.role.value}: {item.content[:300]}" for item in older_messages[-20:])
        system_prompt, user_prompt = self._prompts.conversation_summary_messages(
            session.context_summary, payload
        )
        summary = self._llm_client.generate_text(
            system_prompt=system_prompt, user_prompt=user_prompt
        ).strip()
        if not summary:
            summary = payload[:1200]
        session.context_summary = summary[:3000]
        session.summary_updated_at = messages[-1].created_at if messages else session.updated_at
        session.updated_at = messages[-1].created_at if messages else session.updated_at
        self._repository.save_session(session)

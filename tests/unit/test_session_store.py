import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from orion_agent.core.models import (
    ChatMessage,
    ChatMessageRole,
    ChatSession,
    ChatSessionDetail,
    SessionCreateRequest,
    SessionSummaryRefreshRequest,
    TaskRecord,
    TaskStatus,
    UserProfileFact,
    utcnow,
)
from orion_agent.core.repository import TaskRepository
from orion_agent.core.session_store import SessionStore


class SessionStoreTests(unittest.TestCase):
    """Tests for SessionStore boundary covering session lifecycle operations."""

    def _make_store(self) -> tuple[SessionStore, MagicMock]:
        """Create a SessionStore with a mock repository, profile_manager, llm_client, and prompts."""
        mock_repo = MagicMock()
        mock_profile = MagicMock()
        mock_llm = MagicMock()
        mock_prompts = MagicMock()
        mock_profile.snapshot.return_value = []
        store = SessionStore(mock_repo, mock_profile, mock_llm, mock_prompts)
        return store, mock_repo

    # --- create_session ---

    def test_create_session_basic(self) -> None:
        # 场景：create_session 创建新对话并保存到 repository。
        store, mock_repo = self._make_store()
        mock_repo.save_session.side_effect = lambda s: s

        session = store.create_session(SessionCreateRequest(title="测试对话"))

        self.assertEqual(session.title, "测试对话")
        mock_repo.save_session.assert_called_once()

    def test_create_session_defaults_to_new_dialogue(self) -> None:
        # 场景：未提供 title 时默认为"新对话"。
        store, mock_repo = self._make_store()
        mock_repo.save_session.side_effect = lambda s: s

        session = store.create_session(None)

        self.assertEqual(session.title, "新对话")

    def test_create_session_with_source_branches_messages(self) -> None:
        # 场景：source_session_id 不为空时，从源会话复制最近 6 条消息。
        store, mock_repo = self._make_store()
        source_messages = [
            ChatMessage(session_id="src", role=ChatMessageRole.USER, content="Hello"),
            ChatMessage(session_id="src", role=ChatMessageRole.ASSISTANT, content="Hi there"),
        ]
        source_session = ChatSession(id="src", title="Source Session")
        # repository returns ChatSession for get_session; get_session public method builds ChatSessionDetail
        mock_repo.get_session.side_effect = lambda sid: source_session if sid == "src" else None
        mock_repo.list_session_messages.return_value = source_messages
        mock_repo.list_by_session.return_value = []
        mock_repo.save_session.side_effect = lambda s: s

        session = store.create_session(
            SessionCreateRequest(title="Branch", source_session_id="src")
        )

        # Should have called save_session_message for each source message
        self.assertEqual(mock_repo.save_session_message.call_count, 2)

    def test_create_session_with_seed_prompt_injects_system_message(self) -> None:
        # 场景：提供 seed_prompt 时，在复制消息前注入系统说明消息。
        store, mock_repo = self._make_store()
        source_session = ChatSession(id="src", title="Source Session")
        # repository returns ChatSession; get_session builds ChatSessionDetail internally
        mock_repo.get_session.side_effect = lambda sid: source_session if sid == "src" else None
        mock_repo.list_session_messages.return_value = []
        mock_repo.list_by_session.return_value = []
        mock_repo.save_session.side_effect = lambda s: s

        store.create_session(
            SessionCreateRequest(title="Branch", source_session_id="src", seed_prompt="Continue previous discussion")
        )

        # First call should be the seed_prompt system message
        first_call_msg = mock_repo.save_session_message.call_args_list[0][0][0]
        self.assertEqual(first_call_msg.role, ChatMessageRole.SYSTEM)
        self.assertIn("Continue previous discussion", first_call_msg.content)

    # --- list_sessions ---

    def test_list_sessions_returns_repository_sessions(self) -> None:
        # 场景：list_sessions 委托 repository.list_sessions。
        store, mock_repo = self._make_store()
        sessions = [ChatSession(title="对话1"), ChatSession(title="对话2")]
        mock_repo.list_sessions.return_value = sessions

        result = store.list_sessions(limit=20)

        mock_repo.list_sessions.assert_called_once_with(limit=20)
        self.assertEqual(len(result), 2)

    def test_list_sessions_by_source(self) -> None:
        # 场景：list_sessions_by_source 返回分叉自指定会话的会话列表。
        store, mock_repo = self._make_store()
        mock_repo.list_sessions_by_source.return_value = [ChatSession(title="分支1")]

        result = store.list_sessions_by_source("src_session", limit=10)

        mock_repo.list_sessions_by_source.assert_called_once_with("src_session", limit=10)
        self.assertEqual(len(result), 1)

    # --- get_session ---

    def test_get_session_returns_detail_with_messages_and_tasks(self) -> None:
        # 场景：get_session 返回 ChatSessionDetail，包含 messages 和 tasks。
        store, mock_repo = self._make_store()
        session = ChatSession(id="s1", title="测试")
        messages = [ChatMessage(session_id="s1", role=ChatMessageRole.USER, content="你好")]
        mock_repo.get_session.return_value = session
        mock_repo.list_session_messages.return_value = messages
        mock_repo.list_by_session.return_value = []

        detail = store.get_session("s1")

        self.assertIsNotNone(detail)
        self.assertEqual(detail.session.id, "s1")
        self.assertEqual(len(detail.messages), 1)
        self.assertEqual(len(detail.tasks), 0)

    def test_get_session_returns_none_for_unknown_id(self) -> None:
        # 场景：get_session 对不存在的 session_id 返回 None。
        store, mock_repo = self._make_store()
        mock_repo.get_session.return_value = None

        result = store.get_session("nonexistent")

        self.assertIsNone(result)

    # --- refresh_session_summary ---

    def test_refresh_session_summary_compresses_context(self) -> None:
        # 场景：refresh_session_summary 调用压缩逻辑后返回更新后的 session detail。
        store, mock_repo = self._make_store()
        session = ChatSession(id="s1", title="测试")
        messages = [
            ChatMessage(session_id="s1", role=ChatMessageRole.USER, content=f"消息{i}")
            for i in range(10)
        ]
        mock_repo.get_session.return_value = session
        mock_repo.list_session_messages.return_value = messages
        mock_repo.list_by_session.return_value = []
        mock_prompts = MagicMock()
        mock_prompts.conversation_summary_messages.return_value = ("sys", "user")
        mock_llm = MagicMock()
        mock_llm.generate_text.return_value = MagicMock(
            strip=MagicMock(return_value="压缩后的摘要")
        )
        store._prompts = mock_prompts
        store._llm_client = mock_llm

        detail = store.refresh_session_summary("s1", SessionSummaryRefreshRequest(force=True))

        mock_llm.generate_text.assert_called_once()
        mock_repo.save_session.assert_called()

    def test_refresh_session_summary_returns_none_for_missing_session(self) -> None:
        # 场景：session 不存在时 refresh_session_summary 返回 None。
        store, mock_repo = self._make_store()
        mock_repo.get_session.return_value = None

        result = store.refresh_session_summary("nonexistent")

        self.assertIsNone(result)

    # --- append_message ---

    def test_append_message_creates_session_if_missing(self) -> None:
        # 场景：append_message 在 session_id 对话不存在时先创建会话。
        store, mock_repo = self._make_store()
        mock_repo.get_session.return_value = None
        mock_repo.save_session.side_effect = lambda s: s

        result = store.append_message("new_session", ChatMessageRole.USER, "Hello")

        self.assertIsNotNone(result)
        mock_repo.save_session.assert_called()  # called once for creating session + once after message
        mock_repo.save_session_message.assert_called_once()

    def test_append_message_increments_message_count(self) -> None:
        # 场景：append_message 正确更新 session.message_count 并保存。
        store, mock_repo = self._make_store()
        session = ChatSession(id="s1", title="测试", message_count=0)
        mock_repo.get_session.return_value = session
        mock_repo.save_session.side_effect = lambda s: s

        store.append_message("s1", ChatMessageRole.USER, "你好", task_id="t1")

        self.assertEqual(session.message_count, 1)
        self.assertEqual(session.last_task_id, "t1")
        mock_repo.save_session.assert_called()

    def test_append_message_skips_empty_content(self) -> None:
        # 场景：内容为空时不创建消息也不保存会话。
        store, mock_repo = self._make_store()

        result = store.append_message("s1", ChatMessageRole.USER, "")

        self.assertIsNone(result)
        mock_repo.save_session_message.assert_not_called()

    def test_append_message_skips_empty_session_id(self) -> None:
        # 场景：session_id 为空时不创建消息。
        store, mock_repo = self._make_store()

        result = store.append_message(None, ChatMessageRole.USER, "你好")

        self.assertIsNone(result)

    # --- touch_session ---

    def test_touch_session_updates_last_task_and_title(self) -> None:
        # 场景：touch_session 更新 session.last_task_id，并在标题为默认时更新标题。
        store, mock_repo = self._make_store()
        session = ChatSession(id="s1", title="新对话", message_count=5)
        mock_repo.get_session.return_value = session
        mock_repo.save_session.side_effect = lambda s: s
        profile_hit = MagicMock()
        profile_hit.label = "语言"
        profile_hit.value = "Python"

        store.touch_session("s1", last_task_id="t99", task_title="完成的任务", profile_hits=[profile_hit])

        self.assertEqual(session.last_task_id, "t99")
        self.assertEqual(session.title, "完成的任务")
        self.assertEqual(len(session.profile_snapshot), 1)
        mock_repo.save_session.assert_called()

    def test_touch_session_preserves_existing_title(self) -> None:
        # 场景：session 已有自定义标题时不覆盖。
        store, mock_repo = self._make_store()
        session = ChatSession(id="s1", title="已有的标题", message_count=5)
        mock_repo.get_session.return_value = session
        mock_repo.save_session.side_effect = lambda s: s

        store.touch_session("s1", last_task_id="t1", task_title="新任务", profile_hits=[])

        self.assertEqual(session.title, "已有的标题")

    def test_touch_session_handles_missing_session(self) -> None:
        # 场景：session 不存在时 touch_session 为空操作。
        store, mock_repo = self._make_store()
        mock_repo.get_session.return_value = None

        store.touch_session("nonexistent", last_task_id="t1", task_title="t", profile_hits=[])

        mock_repo.save_session.assert_not_called()

    def test_touch_session_handles_none_session_id(self) -> None:
        # 场景：session_id 为 None 时 touch_session 为空操作。
        store, mock_repo = self._make_store()

        store.touch_session(None, last_task_id="t1", task_title="t", profile_hits=[])

        mock_repo.get_session.assert_not_called()

    # --- get_trace_lookup ---

    def test_get_trace_lookup_returns_session_metadata(self) -> None:
        # 场景：get_trace_lookup 返回 session 的追踪元数据字典。
        store, mock_repo = self._make_store()
        session = ChatSession(
            id="s1",
            title="Test Session",
            message_count=10,
            last_task_id="t5",
            source_session_id="src1",
            profile_snapshot=["lang: Python"],
            context_summary="Session summary here",
        )
        mock_repo.get_session.return_value = session

        trace = store.get_trace_lookup("s1")

        self.assertEqual(trace["session_id"], "s1")
        self.assertEqual(trace["title"], "Test Session")
        self.assertEqual(trace["message_count"], 10)
        self.assertEqual(trace["last_task_id"], "t5")
        self.assertEqual(trace["source_session_id"], "src1")
        self.assertEqual(trace["profile_snapshot_size"], 1)
        self.assertEqual(trace["context_summary_length"], 20)

    def test_get_trace_lookup_empty_for_none_session(self) -> None:
        # 场景：session 不存在时 get_trace_lookup 返回空字典。
        store, mock_repo = self._make_store()
        mock_repo.get_session.return_value = None

        trace = store.get_trace_lookup("nonexistent")

        self.assertEqual(trace, {})

    def test_get_trace_lookup_empty_for_none_session_id(self) -> None:
        # 场景：session_id 为 None 时 get_trace_lookup 返回空字典。
        store, mock_repo = self._make_store()

        trace = store.get_trace_lookup(None)

        self.assertEqual(trace, {})

    def test_list_sessions_by_source_delegates_directly_to_repository_filter(self) -> None:
        # 场景：分叉会话查询应直接委托带 source_session_id 条件的仓储接口，不能退化成只扫描最近会话窗口。
        store, mock_repo = self._make_store()
        mock_repo.list_sessions_by_source.return_value = [ChatSession(title="branch")]

        result = store.list_sessions_by_source("origin_session", limit=5)

        self.assertEqual(len(result), 1)
        mock_repo.list_sessions_by_source.assert_called_once_with("origin_session", limit=5)
        mock_repo.list_sessions.assert_not_called()


class SessionStoreRepositoryBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = TaskRepository(db_path=":memory:")

    def tearDown(self) -> None:
        self.repository.close()

    def test_list_sessions_by_source_queries_all_matching_branches(self) -> None:
        # 场景：当近期大量无关会话存在时，仍然能查到较早的分叉会话，不能只扫描最近窗口。
        origin = ChatSession(id="origin", title="origin")
        self.repository.save_session(origin)

        for index in range(12):
            branched = ChatSession(
                id=f"branch_{index}",
                title=f"branch {index}",
                source_session_id="origin",
            )
            self.repository.save_session(branched)

        for index in range(40):
            unrelated = ChatSession(id=f"noise_{index}", title=f"noise {index}")
            self.repository.save_session(unrelated)

        result = self.repository.list_sessions_by_source("origin", limit=12)

        self.assertEqual(len(result), 12)
        self.assertTrue(all(item.source_session_id == "origin" for item in result))


if __name__ == "__main__":
    unittest.main()

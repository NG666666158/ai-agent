import unittest
import sys
import types

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class OpenAI:  # pragma: no cover - test stub
        def __init__(self, *args, **kwargs) -> None:
            pass

    openai_stub.OpenAI = OpenAI
    sys.modules["openai"] = openai_stub

from orion_agent.core.memory import LongTermMemoryManager
from orion_agent.core.models import LongTermMemoryRecord, MemoryStatus
from orion_agent.core.profile import UserProfileManager
from orion_agent.core.repository import TaskRepository
from orion_agent.core.vector_store import LocalVectorStore


class StubEmbedder:
    def embed(self, text: str) -> list[float]:
        base = sum(ord(char) for char in text) % 97
        return [float(base), float(len(text) or 1), 1.0]

    def health(self) -> dict[str, str]:
        return {"provider": "stub", "mode": "test"}


class ProfileAndMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = TaskRepository(db_path=":memory:")
        self.profile_manager = UserProfileManager(self.repository)
        self.memory_manager = LongTermMemoryManager(
            repository=self.repository,
            embedder=StubEmbedder(),
            vector_store=LocalVectorStore(repository=self.repository),
        )

    def tearDown(self) -> None:
        self.repository.close()

    def test_extract_facts_supports_chinese_learning_preference(self) -> None:
        # 边界：中文偏好表达不能因为编码回归而失效。
        facts = self.profile_manager.extract_facts("我想学 java，我也想学 python")
        values = sorted(item.value for item in facts)
        self.assertIn("Java", values)
        self.assertIn("Python", values)

    def test_match_relevant_supports_chinese_query_keywords(self) -> None:
        # 场景：中文“最想学什么语言”必须命中画像检索。
        for fact in self.profile_manager.extract_facts("我最想学 rust"):
            self.profile_manager.remember(fact)

        matched = self.profile_manager.match_relevant("你知道我最想学的语言是什么吗")
        self.assertTrue(matched)
        self.assertEqual(matched[0].value, "Rust")

    def test_memory_type_weight_supports_chinese_queries(self) -> None:
        # 场景：中文偏好类问题应对 preference 记忆进行权重提升。
        record = LongTermMemoryRecord(
            topic="学习偏好",
            summary="用户更想学 Java",
            details="用户明确表示最近想学 Java。",
            memory_type="preference",
        )
        boosted = self.memory_manager._memory_type_weight(query="你知道我想学什么语言吗", record=record)
        neutral = self.memory_manager._memory_type_weight(query="给我一份部署文档", record=record)
        self.assertGreater(boosted, neutral)

    def test_recall_updates_access_metadata(self) -> None:
        # 场景：recall() 更新记忆的访问元数据（last_accessed_at 和 accessed_count）。
        record = LongTermMemoryRecord(
            topic="测试记忆",
            summary="这是一个测试记忆",
            details="详细内容",
            memory_type="fact",
            governance_flags=set(),
        )
        saved = self.memory_manager.remember(record)
        self.assertEqual(saved.accessed_count, 0)
        self.assertIsNone(saved.last_accessed_at)

        recalled = self.memory_manager.recall("测试记忆", scope="default", limit=5)
        # The recalled record should have updated access metadata
        self.assertGreaterEqual(recalled[0].accessed_count, 1)
        self.assertIsNotNone(recalled[0].last_accessed_at)

    def test_long_term_memory_record_has_governance_fields(self) -> None:
        # 场景：LongTermMemoryRecord 包含治理必需字段。
        record = LongTermMemoryRecord(
            topic="测试",
            summary="摘要",
            details="详情",
            governance_flags={"auto_extracted"},
        )
        self.assertIsInstance(record.governance_flags, set)
        self.assertIn("auto_extracted", record.governance_flags)
        self.assertEqual(record.status, MemoryStatus.ACTIVE)
        self.assertEqual(record.accessed_count, 0)
        self.assertIsNone(record.last_accessed_at)

    def test_match_relevant_updates_access_metadata(self) -> None:
        # 场景：match_relevant() 更新画像的访问元数据。
        facts = self.profile_manager.extract_facts("我想学 python")
        for fact in facts:
            self.profile_manager.remember(fact)

        # Reset accessed_count to 0 for test
        fact_id = facts[0].id
        stored = self.profile_manager.get_fact(fact_id)
        stored.accessed_count = 0
        stored.last_accessed_at = None
        self.profile_manager.repository.save_user_profile_fact(stored)

        matched = self.profile_manager.match_relevant("我想学 python", limit=5)
        self.assertGreaterEqual(matched[0].accessed_count, 1)
        self.assertIsNotNone(matched[0].last_accessed_at)

    def test_user_profile_fact_has_governance_fields(self) -> None:
        # 场景：UserProfileFact 包含治理必需字段。
        from orion_agent.core.models import UserProfileFact, UserProfileFactStatus

        fact = UserProfileFact(
            category="learning_language",
            label="学习语言",
            value="Python",
            governance_flags={"auto_extracted"},
        )
        self.assertIsInstance(fact.governance_flags, set)
        self.assertIn("auto_extracted", fact.governance_flags)
        self.assertEqual(fact.status, UserProfileFactStatus.ACTIVE)
        self.assertEqual(fact.accessed_count, 0)
        self.assertIsNone(fact.last_accessed_at)


if __name__ == "__main__":
    unittest.main()

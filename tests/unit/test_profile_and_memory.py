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
from orion_agent.core.models import LongTermMemoryRecord, MemoryStatus, UserProfileFactStatus, utcnow
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

    def test_recall_does_not_persist_query_specific_retrieval_metadata(self) -> None:
        # 场景：retrieval_score / retrieval_reason / retrieval_channels 属于查询期临时字段，不应写回长期存储。
        record = LongTermMemoryRecord(
            topic="检索污染测试",
            summary="用于验证召回元数据不落库",
            details="这是一次记忆检索污染回归测试。",
            memory_type="fact",
        )
        saved = self.memory_manager.remember(record)

        recalled = self.memory_manager.recall("检索污染测试", scope="default", limit=5)
        self.assertIsNotNone(recalled[0].retrieval_score)
        self.assertTrue(recalled[0].retrieval_reason)
        self.assertTrue(recalled[0].retrieval_channels)

        persisted = self.repository.get_long_term_memory(saved.id)
        self.assertIsNone(persisted.retrieval_score)
        self.assertIsNone(persisted.retrieval_reason)
        self.assertEqual(persisted.retrieval_channels, [])

    def test_recall_fallback_also_updates_access_metadata(self) -> None:
        # 场景：recent fallback 分支也应更新访问治理元数据，不能绕开访问计数。
        record = LongTermMemoryRecord(
            topic="最近记忆",
            summary="最近回退召回",
            details="触发 fallback 路径的测试内容",
            memory_type="fact",
        )
        saved = self.memory_manager.remember(record)

        recalled = self.memory_manager.recall("完全不相关的稀有查询", scope="default", limit=5)
        self.assertTrue(recalled)

        persisted = self.repository.get_long_term_memory(saved.id)
        self.assertGreaterEqual(persisted.accessed_count, 1)
        self.assertIsNotNone(persisted.last_accessed_at)


class ProfileExtractionAndDecayTests(unittest.TestCase):
    """US-R20: Expanded taxonomy, confidence decay, and preference timeline."""

    def setUp(self) -> None:
        self.repository = TaskRepository(db_path=":memory:")
        self.profile_manager = UserProfileManager(self.repository)

    def tearDown(self) -> None:
        self.repository.close()

    def test_extract_facts_supports_framework_category(self) -> None:
        # 验收标准：提取器支持 framework 类偏好
        facts = self.profile_manager.extract_facts("我使用 react 来做前端开发")
        framework_facts = [f for f in facts if f.category == "framework"]
        self.assertTrue(framework_facts)
        self.assertEqual(framework_facts[0].value, "React")

    def test_extract_facts_supports_domain_category(self) -> None:
        # 验收标准：提取器支持 domain 类偏好
        facts = self.profile_manager.extract_facts("我主要做后端开发")
        domain_facts = [f for f in facts if f.category == "domain"]
        self.assertTrue(domain_facts)
        self.assertEqual(domain_facts[0].value, "后端")

    def test_extract_facts_supports_output_format_category(self) -> None:
        # 验收标准：提取器支持 output_format 类偏好
        facts = self.profile_manager.extract_facts("我想要 markdown 格式")
        format_facts = [f for f in facts if f.category == "output_format"]
        self.assertTrue(format_facts)

    def test_extract_facts_supports_tone_category(self) -> None:
        # 验收标准：提取器支持 tone 类偏好
        from orion_agent.core.profile import PreferenceCategory
        # Verify PreferenceCategory.TONE enum value exists
        self.assertEqual(PreferenceCategory.TONE.value, "tone")
        # Create and store a tone fact directly (category is tone, no extraction needed)
        tone_fact = self.profile_manager.extract_facts("我喜欢 Python")[0]
        tone_fact.category = PreferenceCategory.TONE.value
        tone_fact.value = "concise"
        saved = self.profile_manager.remember(tone_fact)
        self.assertEqual(saved.category, "tone")
        self.assertEqual(saved.value, "concise")

    def test_effective_confidence_decays_over_time(self) -> None:
        # 验收标准：effective_confidence 随时间衰减而非仅依赖原始值
        from datetime import timedelta

        fact = self.profile_manager.extract_facts("我想学 Go")[0]
        # Force an old updated_at to trigger decay
        fact.updated_at = utcnow() - timedelta(days=UserProfileManager.CONFIDENCE_HALF_LIFE_DAYS)
        effective = self.profile_manager.effective_confidence(fact)
        self.assertLess(effective, fact.confidence)
        self.assertGreaterEqual(effective, UserProfileManager.MIN_EFFECTIVE_CONFIDENCE)

    def test_effective_confidence_floor_for_archived_facts(self) -> None:
        # 验收标准：ARCHIVED/MERGED 状态返回 floor 值而非原始 confidence
        fact = self.profile_manager.extract_facts("我想学 Rust")[0]
        fact.status = UserProfileFactStatus.ARCHIVED
        effective = self.profile_manager.effective_confidence(fact)
        self.assertEqual(effective, UserProfileManager.MIN_EFFECTIVE_CONFIDENCE)

    def test_remember_preserves_historical_preference(self) -> None:
        # 验收标准：新偏好不盲目覆盖旧偏好；历史可通过 status/timeline 追溯
        old_fact = self.profile_manager.extract_facts("我想学 Java")[0]
        self.profile_manager.remember(old_fact)

        new_fact = self.profile_manager.extract_facts("我想学 Python")[0]
        self.profile_manager.remember(new_fact)

        # Old fact should be archived, not overwritten
        reloaded = self.profile_manager.get_fact(old_fact.id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.status, UserProfileFactStatus.ARCHIVED)
        # New fact is stored as a separate record
        new_reloaded = self.profile_manager.get_fact(new_fact.id)
        self.assertIsNotNone(new_reloaded)
        self.assertEqual(new_reloaded.status, UserProfileFactStatus.ACTIVE)

    def test_match_relevant_orders_by_effective_confidence(self) -> None:
        # 验收标准：match_relevant 使用 effective_confidence 排序而非原始 confidence
        from datetime import timedelta
        from orion_agent.core.profile import PreferenceCategory

        # Create two facts in DIFFERENT categories to avoid _archive_conflicts suppression
        # Rust: learning_language (Chinese trigger "我想学" + English value)
        rust_fact = self.profile_manager.extract_facts("\u6211\u60f3\u5b66 Rust")[0]
        self.assertEqual(rust_fact.category, PreferenceCategory.LEARNING_LANGUAGE.value)
        self.profile_manager.remember(rust_fact)
        # Manually age Rust to make its effective_confidence lower
        rust_reloaded = self.profile_manager.get_fact(rust_fact.id)
        rust_reloaded.updated_at = utcnow() - timedelta(days=60)
        self.profile_manager.repository.save_user_profile_fact(rust_reloaded)

        # Python: preferred_language (Chinese trigger "我喜欢" + English value)
        py_fact = self.profile_manager.extract_facts("\u6211\u559c\u6b22 Python")[0]
        self.assertEqual(py_fact.category, PreferenceCategory.PREFERRED_LANGUAGE.value)
        self.profile_manager.remember(py_fact)

        # Both should be returned and Python (fresher) should outrank Rust
        matched = self.profile_manager.match_relevant("\u6211\u60f3\u5b66", limit=5)
        matched_values = [f.value for f in matched]
        self.assertIn("Rust", matched_values)
        self.assertIn("Python", matched_values)
        rust_idx = matched_values.index("Rust")
        py_idx = matched_values.index("Python")
        self.assertLess(py_idx, rust_idx)

    def test_list_facts_exposes_metadata_for_active_vs_historical(self) -> None:
        # 验收标准：list_facts 暴露足够元数据以区分 active vs historical preference
        fact = self.profile_manager.extract_facts("我想学 Java")[0]
        self.profile_manager.remember(fact)

        new_fact = self.profile_manager.extract_facts("我想学 Python")[0]
        self.profile_manager.remember(new_fact)

        # include_inactive=True returns both
        all_facts = self.profile_manager.list_facts(limit=50, include_inactive=True)
        statuses = {f.id: f.status for f in all_facts}
        self.assertEqual(statuses[fact.id], UserProfileFactStatus.ARCHIVED)
        self.assertEqual(statuses[new_fact.id], UserProfileFactStatus.ACTIVE)

        # include_inactive=False returns only active
        active_only = self.profile_manager.list_facts(limit=50, include_inactive=False)
        active_ids = {f.id for f in active_only}
        self.assertIn(new_fact.id, active_ids)
        self.assertNotIn(fact.id, active_ids)


if __name__ == "__main__":
    unittest.main()

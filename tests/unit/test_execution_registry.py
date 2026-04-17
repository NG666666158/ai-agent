import unittest

from orion_agent.core.execution_registry import (
    EXECUTION_STAGES,
    ExecutionStage,
    get_stage,
    stage_short_label,
    stage_title,
)


class ExecutionRegistryTests(unittest.TestCase):
    def test_stages_cover_all_known_kinds(self) -> None:
        # 场景：EXECUTION_STAGES 包含所有已知的执行阶段 kind。
        known_kinds = [
            "query_rewrite",
            "prompt_assembly",
            "vector_retrieval",
            "multi_recall",
            "progress",
            "step",
            "tool",
            "recovery",
            "answer_generation",
            "review",
        ]
        for kind in known_kinds:
            self.assertIn(kind, EXECUTION_STAGES, f"kind '{kind}' should be in EXECUTION_STAGES")

    def test_stage_fields(self) -> None:
        # 场景：每个 ExecutionStage 有 kind、title 和 short_label。
        for kind, stage in EXECUTION_STAGES.items():
            self.assertEqual(stage.kind, kind)
            self.assertTrue(stage.title)
            self.assertTrue(stage.short_label)

    def test_get_stage_returns_stage_for_known_kind(self) -> None:
        # 场景：get_stage 对已知 kind 返回 ExecutionStage。
        stage = get_stage("query_rewrite")
        self.assertIsInstance(stage, ExecutionStage)
        self.assertEqual(stage.title, "Query 改写与任务标准化")
        self.assertEqual(stage.short_label, "Query 改写")

    def test_get_stage_returns_none_for_unknown_kind(self) -> None:
        # 场景：get_stage 对未知 kind 返回 None。
        self.assertIsNone(get_stage("unknown_stage"))

    def test_stage_title_returns_title_for_known_kind(self) -> None:
        # 场景：stage_title 对已知 kind 返回 title。
        self.assertEqual(stage_title("recovery"), "恢复与重规划")

    def test_stage_title_returns_kind_for_unknown_kind(self) -> None:
        # 场景：stage_title 对未知 kind 返回 kind 本身作为默认值。
        self.assertEqual(stage_title("unknown"), "unknown")

    def test_stage_title_accepts_custom_default(self) -> None:
        self.assertEqual(stage_title("unknown", default="默认值"), "默认值")

    def test_stage_short_label_returns_short_label_for_known_kind(self) -> None:
        # 场景：stage_short_label 对已知 kind 返回 short_label。
        self.assertEqual(stage_short_label("tool"), "工具调用")

    def test_stage_short_label_returns_kind_for_unknown_kind(self) -> None:
        self.assertEqual(stage_short_label("unknown"), "unknown")

    def test_short_labels_match_frontend_expectations(self) -> None:
        # 场景：short_label 与前端 toChineseNodeKind 的映射值一致。
        # 前端期望：query_rewrite -> "Query 改写", tool -> "工具调用" 等。
        self.assertEqual(EXECUTION_STAGES["query_rewrite"].short_label, "Query 改写")
        self.assertEqual(EXECUTION_STAGES["tool"].short_label, "工具调用")
        self.assertEqual(EXECUTION_STAGES["recovery"].short_label, "恢复与重规划")
        self.assertEqual(EXECUTION_STAGES["answer_generation"].short_label, "回答生成")


if __name__ == "__main__":
    unittest.main()
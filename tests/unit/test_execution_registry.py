import unittest

from orion_agent.core.execution_registry import (
    EXECUTION_STAGES,
    ExecutionStage,
    get_stage,
    stage_category,
    stage_short_label,
    stage_sort_order,
    stage_title,
)


class ExecutionRegistryTests(unittest.TestCase):
    def test_stages_cover_all_known_kinds(self) -> None:
        # 场景：EXECUTION_STAGES 包含所有已知的执行阶段 kind，包括运行时进度阶段。
        known_kinds = [
            "thinking",
            "query_rewrite",
            "context",
            "prompt_assembly",
            "vector_retrieval",
            "memory",
            "multi_recall",
            "planning",
            "step",
            "running",
            "tool",
            "approval",
            "recovery",
            "replanning",
            "answer_generation",
            "review",
            "completed",
            "failed",
            "queued",
            "cancelled",
            "resume",
            "progress",
        ]
        for kind in known_kinds:
            self.assertIn(kind, EXECUTION_STAGES, f"kind '{kind}' should be in EXECUTION_STAGES")

    def test_stage_fields(self) -> None:
        # 场景：每个 ExecutionStage 都应包含 kind、title、short_label、category 和 sort_order。
        for kind, stage in EXECUTION_STAGES.items():
            self.assertEqual(stage.kind, kind)
            self.assertTrue(stage.title)
            self.assertTrue(stage.short_label)
            self.assertTrue(stage.category)
            self.assertGreater(stage.sort_order, 0)

    def test_get_stage_returns_stage_for_known_kind(self) -> None:
        # 场景：get_stage 对已知 kind 返回 ExecutionStage。
        stage = get_stage("query_rewrite")
        self.assertIsInstance(stage, ExecutionStage)
        self.assertEqual(stage.title, "输入解析与任务标准化")
        self.assertEqual(stage.short_label, "任务解析")
        self.assertEqual(stage.category, "reasoning")

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
        # 场景：未知 kind 时允许使用自定义默认文案。
        self.assertEqual(stage_title("unknown", default="默认值"), "默认值")

    def test_stage_short_label_returns_short_label_for_known_kind(self) -> None:
        # 场景：stage_short_label 对已知 kind 返回 short_label。
        self.assertEqual(stage_short_label("tool"), "工具调用")

    def test_stage_short_label_returns_kind_for_unknown_kind(self) -> None:
        # 场景：stage_short_label 对未知 kind 返回 kind 本身。
        self.assertEqual(stage_short_label("unknown"), "unknown")

    def test_stage_category_returns_category_for_known_kind(self) -> None:
        # 场景：stage_category 应暴露执行阶段分类，供前端和运行时共享。
        self.assertEqual(stage_category("vector_retrieval"), "retrieval")

    def test_stage_sort_order_returns_stable_order(self) -> None:
        # 场景：stage_sort_order 应保证时间戳相同节点仍能稳定排序。
        self.assertLess(stage_sort_order("query_rewrite"), stage_sort_order("tool"))

    def test_short_labels_match_frontend_expectations(self) -> None:
        # 场景：short_label 与前端执行节点的中文标签保持一致。
        self.assertEqual(EXECUTION_STAGES["query_rewrite"].short_label, "任务解析")
        self.assertEqual(EXECUTION_STAGES["tool"].short_label, "工具调用")
        self.assertEqual(EXECUTION_STAGES["recovery"].short_label, "恢复与重规划")
        self.assertEqual(EXECUTION_STAGES["answer_generation"].short_label, "回答生成")

    def test_runtime_progress_stages_have_valid_metadata(self) -> None:
        # 场景：运行时进度阶段（thinking、memory、planning 等）有有效的中文标签。
        runtime_stages = ["thinking", "context", "memory", "planning", "running", "approval", "replanning"]
        for stage_kind in runtime_stages:
            stage = get_stage(stage_kind)
            self.assertIsNotNone(stage, f"stage '{stage_kind}' should be in registry")
            self.assertTrue(stage.title, f"stage '{stage_kind}' should have a title")
            self.assertTrue(stage.short_label, f"stage '{stage_kind}' should have a short_label")
            self.assertIn(stage.category, ["reasoning", "retrieval", "runtime", "recovery", "output"])

    def test_terminal_stages_have_output_category(self) -> None:
        # 场景：完成、失败、取消等终态阶段属于 output 类别。
        terminal_stages = ["completed", "failed", "cancelled"]
        for stage_kind in terminal_stages:
            stage = get_stage(stage_kind)
            self.assertIsNotNone(stage, f"terminal stage '{stage_kind}' should be in registry")
            self.assertEqual(stage.category, "output", f"terminal stage '{stage_kind}' should be in output category")


if __name__ == "__main__":
    unittest.main()

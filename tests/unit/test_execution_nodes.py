import unittest
from datetime import UTC, datetime, timedelta

from orion_agent.core.models import (
    ContextLayer,
    FailureCategory,
    LongTermMemoryRecord,
    ParsedGoal,
    ProgressUpdate,
    ReplanEvent,
    ReplanReason,
    Step,
    StepStatus,
    TaskPhase,
    TaskRecord,
    TaskResponse,
    TaskReview,
    TaskStatus,
    ToolCallStatus,
    ToolInvocation,
    UserProfileFact,
    build_execution_nodes_v2,
)


class ExecutionNodeTests(unittest.TestCase):
    def test_build_execution_nodes_v2_generates_unified_timeline(self) -> None:
        # 场景：统一执行时间线需要覆盖解析、召回、步骤、工具、恢复、回答生成和结果复核节点。
        base_time = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        record = TaskRecord(
            title="请总结当前项目架构并给出优化建议",
            status=TaskStatus.COMPLETED,
            created_at=base_time,
            updated_at=base_time + timedelta(minutes=2),
            parsed_goal=ParsedGoal(
                goal="总结当前项目架构并给出优化建议",
                constraints=["使用中文", "输出 Markdown"],
            ),
            context_layers=ContextLayer(
                system_instructions="你是一个中文 Agent。",
                session_summary="用户正在评估项目结构。",
                condensed_recent_messages=["用户想看统一执行链路"],
                recent_messages=["请总结当前项目架构并给出优化建议"],
                working_memory=["重点关注执行内核与前端控制台"],
                build_notes=["已注入历史会话与长期记忆"],
                source_summary="包含最近一次系统检索摘要",
            ),
            recalled_memories=[
                LongTermMemoryRecord(
                    topic="用户偏好",
                    summary="用户偏好中文回答，并强调项目可追溯能力。",
                    details="用户多次要求中文界面与可视化执行链路。",
                    memory_type="profile_preference",
                    retrieval_score=0.92,
                    retrieval_reason="语义相似度高",
                    retrieval_channels=["vector", "keyword"],
                )
            ],
            profile_hits=[
                UserProfileFact(category="preference", label="语言偏好", value="中文", summary="长期偏好")
            ],
            progress_updates=[
                ProgressUpdate(
                    stage="parsing",
                    message="正在解析输入",
                    detail="已提取目标和约束",
                    created_at=base_time + timedelta(seconds=5),
                )
            ],
            steps=[
                Step(
                    name="Draft Deliverable",
                    description="生成最终回答正文",
                    status=StepStatus.DONE,
                    tool_name="generate_markdown",
                    output="已生成 Markdown 回答。",
                )
            ],
            tool_invocations=[
                ToolInvocation(
                    step_id="step_1",
                    tool_name="web_search",
                    status=ToolCallStatus.SUCCESS,
                    input_payload={"query": "orion agent architecture"},
                    output_preview="已返回 3 条结果。",
                    failure_category=FailureCategory.NONE,
                    attempt_count=1,
                    started_at=base_time + timedelta(seconds=20),
                    completed_at=base_time + timedelta(seconds=25),
                )
            ],
            replan_history=[
                ReplanEvent(
                    reason=ReplanReason.TOOL_FAILURE,
                    summary="搜索失败后切换到本地总结",
                    detail="第一次工具调用失败后，系统改为基于上下文直接生成。",
                    failure_category=FailureCategory.TOOL_TIMEOUT,
                    trigger_phase=TaskPhase.REPLANNING,
                    resume_from_step_name="Draft Deliverable",
                    recovery_strategy="replan_remaining_steps",
                    created_at=base_time + timedelta(seconds=40),
                )
            ],
            live_result="## 回答\n当前项目已经具备原型能力。",
            result="## 回答\n当前项目已经具备原型能力。",
            review=TaskReview(
                passed=True,
                summary="结果覆盖了核心模块。",
                checklist=["已包含架构总结", "已包含优化建议"],
            ),
        )

        nodes = build_execution_nodes_v2(record)

        self.assertGreaterEqual(len(nodes), 8)
        self.assertIn("query_rewrite", [node.kind for node in nodes])
        self.assertIn("prompt_assembly", [node.kind for node in nodes])
        self.assertIn("vector_retrieval", [node.kind for node in nodes])
        self.assertIn("multi_recall", [node.kind for node in nodes])
        self.assertIn("tool", [node.kind for node in nodes])
        self.assertIn("recovery", [node.kind for node in nodes])
        self.assertIn("answer_generation", [node.kind for node in nodes])
        self.assertIn("review", [node.kind for node in nodes])

        query_node = next(node for node in nodes if node.kind == "query_rewrite")
        self.assertEqual(query_node.title, "输入解析与任务标准化")
        self.assertEqual(query_node.artifacts[0].label, "原始输入")

        tool_node = next(node for node in nodes if node.kind == "tool")
        self.assertEqual(tool_node.duration_ms, 5000)
        self.assertEqual(tool_node.status, "done")

        answer_node = next(node for node in nodes if node.kind == "answer_generation")
        self.assertEqual(answer_node.status, "done")
        self.assertIn("当前项目已经具备原型能力", answer_node.detail or "")

    def test_task_response_from_record_uses_unified_execution_nodes(self) -> None:
        # 场景：TaskResponse.from_record 必须自动注入统一执行节点，同时保留旧字段兼容。
        record = TaskRecord(
            title="输出统一执行链路",
            status=TaskStatus.RUNNING,
            parsed_goal=ParsedGoal(goal="输出统一执行链路"),
            progress_updates=[ProgressUpdate(stage="running", message="正在执行", detail="节点正在生成")],
            steps=[Step(name="Draft Deliverable", description="生成回答", status=StepStatus.DOING)],
            live_result="正在生成回答",
        )

        response = TaskResponse.from_record(record)

        self.assertTrue(response.execution_nodes)
        self.assertTrue(response.progress_updates)
        self.assertTrue(response.steps)
        answer_node = next(node for node in response.execution_nodes if node.kind == "answer_generation")
        self.assertEqual(answer_node.status, "doing")


if __name__ == "__main__":
    unittest.main()

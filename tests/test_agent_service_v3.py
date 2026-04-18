import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from orion_agent.core.llm_runtime import FallbackLLMClient
from orion_agent.core.models import (
    FailureCategory,
    FailureResolution,
    LongTermMemoryRecord,
    MemorySource,
    MemoryUpdateRequest,
    MemoryVersion,
    ReplanReason,
    SessionCreateRequest,
    SessionSummaryRefreshRequest,
    TaskApprovalDecisionRequest,
    TaskCreateRequest,
    TaskResumeRequest,
    TaskReview,
    TaskStatus,
    UserProfileFactStatus,
    UserProfileMergeRequest,
    UserProfileUpdateRequest,
)
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService
from orion_agent.core.tools import ToolExecutionError


class AgentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentService(
            repository=TaskRepository(db_path=":memory:"),
            llm_client=FallbackLLMClient(),
        )

    def tearDown(self) -> None:
        self.service.repository.close()

    def test_create_task_completes_mvp_flow(self) -> None:
        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Implement AI Agent MVP",
                constraints=["Focus on project planning workflow", "Output markdown"],
                expected_output="markdown",
                source_text=(
                    "The system should support task parsing, planning, tool usage, "
                    "short-term memory, and structured result delivery."
                ),
                enable_web_search=False,
            )
        )

        self.assertEqual(response.status, TaskStatus.COMPLETED)
        self.assertGreaterEqual(len(response.steps), 5)
        self.assertIn("AI Agent MVP", response.result)
        self.assertTrue(response.review and response.review.passed)
        self.assertGreaterEqual(len(response.tool_invocations), 2)
        self.assertEqual(response.checkpoint.phase.value, "COMPLETED")
        self.assertEqual(response.checkpoint.current_stage, "completed")
        self.assertTrue(response.checkpoint.last_completed_step_name)
        self.assertGreaterEqual(response.checkpoint.context_version, 1)
        self.assertTrue(response.context_layers.layer_budget)
        self.assertTrue(response.context_layers.build_notes)

    def test_context_layers_include_budget_and_condensed_messages(self) -> None:
        session = self.service.create_session(SessionCreateRequest(title="context budget"))
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="First round for context layering",
                expected_output="markdown",
                enable_web_search=False,
                session_id=session.id,
            )
        )
        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Second round to inspect context layering",
                expected_output="markdown",
                enable_web_search=False,
                session_id=session.id,
            )
        )

        self.assertTrue(response.context_layers.recent_messages)
        self.assertTrue(response.context_layers.condensed_recent_messages)
        self.assertIn("recent_messages", response.context_layers.layer_budget)
        self.assertTrue(any("session_summary" in item for item in response.context_layers.build_notes))

    def test_session_history_is_written_for_user_and_assistant(self) -> None:
        session = self.service.create_session(SessionCreateRequest(title="测试会话"))

        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Write a session aware answer",
                expected_output="markdown",
                enable_web_search=False,
                session_id=session.id,
            )
        )

        detail = self.service.get_session(session.id)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(response.session_id, session.id)
        self.assertGreaterEqual(len(detail.messages), 2)
        self.assertEqual(detail.messages[0].role.value, "USER")
        self.assertEqual(detail.messages[-1].role.value, "ASSISTANT")
        self.assertTrue(any(task.id == response.id for task in detail.tasks))

    def test_multi_turn_session_context_is_compressed(self) -> None:
        session = self.service.create_session(SessionCreateRequest(title="多轮压缩测试"))

        for index in range(5):
            self.service.create_and_run_task(
                TaskCreateRequest(
                    goal=f"第 {index + 1} 轮继续完善同一个方案",
                    expected_output="markdown",
                    enable_web_search=False,
                    session_id=session.id,
                )
            )

        detail = self.service.get_session(session.id)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertGreaterEqual(len(detail.messages), 10)
        self.assertTrue(detail.session.context_summary)

    def test_create_task_with_source_file_waits_for_confirmation(self) -> None:
        source_file = Path("AI Agent 项目规划文档.md").resolve()

        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Generate a deliverable from a local document",
                source_path=str(source_file),
                expected_output="markdown",
                enable_web_search=False,
            )
        )

        self.assertEqual(response.status, TaskStatus.WAITING_APPROVAL)
        self.assertEqual(len(response.pending_approvals), 1)
        self.assertEqual(response.pending_approvals[0].tool_name, "read_local_file")

    def test_repository_persists_task_for_listing(self) -> None:
        created = self.service.create_and_run_task(
            TaskCreateRequest(goal="Generate project brief", expected_output="markdown", enable_web_search=False)
        )

        listed = self.service.list_tasks(limit=10)

        self.assertTrue(any(task.id == created.id for task in listed))

    def test_long_term_memory_is_written_and_can_be_managed(self) -> None:
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Prepare AI Agent roadmap",
                expected_output="markdown",
                enable_web_search=False,
                memory_scope="roadmap",
            )
        )

        memories = self.service.list_memories(scope="roadmap", limit=10)
        self.assertGreaterEqual(len(memories), 1)
        self.assertTrue(self.service.delete_memory(memories[0].id))
        self.assertEqual(self.service.list_memories(scope="roadmap", limit=10), [])

    def test_long_term_memory_can_be_updated(self) -> None:
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Prepare editable memory entry",
                expected_output="markdown",
                enable_web_search=False,
                memory_scope="editable",
            )
        )

        memories = self.service.list_memories(scope="editable", limit=10)
        self.assertGreaterEqual(len(memories), 1)

        updated = self.service.update_memory(
            memories[0].id,
            MemoryUpdateRequest(
                topic="Edited memory topic",
                summary="Edited summary",
                details="Edited details",
                tags=["edited", "memory"],
            ),
        )

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.topic, "Edited memory topic")
        self.assertEqual(updated.summary, "Edited summary")
        self.assertEqual(updated.details, "Edited details")
        self.assertEqual(updated.tags, ["edited", "memory"])
        self.assertGreaterEqual(len(updated.versions), 2)
        self.assertEqual(updated.versions[-1].updated_by, "editor")

    def test_branched_session_copies_recent_context(self) -> None:
        parent = self.service.create_session(SessionCreateRequest(title="父会话"))

        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="先生成一段父会话上下文",
                expected_output="markdown",
                enable_web_search=False,
                session_id=parent.id,
            )
        )

        branched = self.service.create_session(
            SessionCreateRequest(
                title="子分支会话",
                source_session_id=parent.id,
                seed_prompt="延续父会话，但聚焦测试策略。",
            )
        )
        detail = self.service.get_session(branched.id)

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.session.source_session_id, parent.id)
        self.assertGreaterEqual(len(detail.messages), 3)
        self.assertEqual(detail.messages[0].role.value, "SYSTEM")
        self.assertIn("聚焦测试策略", detail.messages[0].content)

    def test_refresh_session_summary_forces_summary_generation(self) -> None:
        session = self.service.create_session(SessionCreateRequest(title="摘要刷新测试"))

        for index in range(2):
            self.service.create_and_run_task(
                TaskCreateRequest(
                    goal=f"生成第 {index + 1} 轮摘要上下文",
                    expected_output="markdown",
                    enable_web_search=False,
                    session_id=session.id,
                )
            )

        refreshed = self.service.refresh_session_summary(session.id, SessionSummaryRefreshRequest(force=True))

        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertTrue(refreshed.session.context_summary)
        self.assertIsNotNone(refreshed.session.summary_updated_at)

    def test_memory_soft_delete_hides_record_but_preserves_audit_fields(self) -> None:
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="写入一条待软删除记忆",
                expected_output="markdown",
                enable_web_search=False,
                memory_scope="governance",
            )
        )

        memories = self.service.list_memories(scope="governance", limit=10)
        self.assertGreaterEqual(len(memories), 1)

        deleted = self.service.delete_memory(memories[0].id)
        stored = self.service.repository.get_long_term_memory(memories[0].id)

        self.assertTrue(deleted)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertTrue(stored.deleted)
        self.assertIsNotNone(stored.deleted_at)
        self.assertEqual(self.service.list_memories(scope="governance", limit=10), [])

    def test_cross_session_profile_is_extracted_and_matched(self) -> None:
        first_session = self.service.create_session(SessionCreateRequest(title="偏好采集"))
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="我想学java，告诉我学习路线",
                expected_output="markdown",
                enable_web_search=False,
                session_id=first_session.id,
            )
        )

        profile_facts = self.service.list_user_profile_facts(limit=10)
        self.assertTrue(any(fact.value == "Java" for fact in profile_facts))

        second_session = self.service.create_session(SessionCreateRequest(title="新会话"))
        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="你知道我最想学的语言是什么吗",
                expected_output="markdown",
                enable_web_search=False,
                session_id=second_session.id,
            )
        )

        self.assertTrue(any(hit.value == "Java" for hit in response.profile_hits))
        self.assertTrue(any("学习语言偏好" in item for item in response.context_layers.profile_facts))

    def test_backend_citation_map_references_profile_source(self) -> None:
        first_session = self.service.create_session(SessionCreateRequest(title="citation profile collect"))
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="我想学 java，告诉我学习路线",
                expected_output="markdown",
                enable_web_search=False,
                session_id=first_session.id,
            )
        )

        second_session = self.service.create_session(SessionCreateRequest(title="citation profile answer"))
        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="你知道我最想学的语言是什么吗，请直接回答并解释",
                expected_output="markdown",
                enable_web_search=False,
                session_id=second_session.id,
            )
        )

        profile_source_ids = {item.id for item in response.citation_sources if item.kind == "profile"}
        cited_source_ids = {source_id for item in response.paragraph_citations for source_id in item.source_ids}

        self.assertTrue(profile_source_ids)
        self.assertTrue(response.paragraph_citations)
        self.assertTrue(profile_source_ids & cited_source_ids)

    def test_mixed_recall_returns_scores_reasons_and_weighted_type(self) -> None:
        preference = LongTermMemoryRecord(
            scope="rag",
            memory_type="preference",
            topic="学习语言偏好",
            summary="用户当前最想学 Java。",
            details="用户明确表示最想学 Java，并希望得到学习路线建议。",
            tags=["java", "preference"],
            source=MemorySource(source_type="profile"),
            versions=[
                MemoryVersion(
                    version=1,
                    topic="学习语言偏好",
                    summary="用户当前最想学 Java。",
                    details="用户明确表示最想学 Java，并希望得到学习路线建议。",
                    tags=["java", "preference"],
                    updated_by="seed",
                )
            ],
        )
        task_result = LongTermMemoryRecord(
            scope="rag",
            memory_type="task_result",
            topic="Java 学习路线输出",
            summary="生成过一份 Java 学习路线。",
            details="这是一份围绕 Java 基础、集合、并发和项目实践的学习路线。",
            tags=["java", "roadmap"],
            source=MemorySource(source_type="task_result"),
            versions=[
                MemoryVersion(
                    version=1,
                    topic="Java 学习路线输出",
                    summary="生成过一份 Java 学习路线。",
                    details="这是一份围绕 Java 基础、集合、并发和项目实践的学习路线。",
                    tags=["java", "roadmap"],
                    updated_by="seed",
                )
            ],
        )
        self.service.long_term_memory.remember(preference)
        self.service.long_term_memory.remember(task_result)

        recalled = self.service.search_memories(query="你知道我最想学的语言是什么吗", scope="rag", limit=2)

        self.assertGreaterEqual(len(recalled), 1)
        self.assertEqual(recalled[0].memory_type, "preference")
        self.assertIsNotNone(recalled[0].retrieval_score)
        self.assertTrue(recalled[0].retrieval_reason)
        self.assertTrue(recalled[0].retrieval_channels)
        self.assertIn("type_boost=preference", recalled[0].retrieval_reason)

    def test_vector_memory_prefers_semantic_match(self) -> None:
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Prepare frontend dashboard plan",
                expected_output="markdown",
                enable_web_search=False,
                memory_scope="semantic",
            )
        )
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Document memory retrieval design",
                expected_output="markdown",
                enable_web_search=False,
                memory_scope="semantic",
            )
        )

        recalled = self.service.search_memories(query="frontend dashboard", scope="semantic", limit=1)

        self.assertEqual(len(recalled), 1)
        self.assertIn("frontend", recalled[0].topic.lower())

    def test_task_evaluation_reports_quality_score(self) -> None:
        created = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Evaluate AI Agent MVP output",
                expected_output="markdown",
                enable_web_search=False,
            )
        )

        evaluation = self.service.evaluate_task(created.id)

        self.assertIsNotNone(evaluation)
        self.assertGreaterEqual(evaluation.score, 0.8)
        self.assertTrue(any("task completed" in item for item in evaluation.checks))

    def test_create_task_async_eventually_completes(self) -> None:
        launched = self.service.create_task_async(
            TaskCreateRequest(
                goal="Stream task progress for the UI",
                expected_output="markdown",
                enable_web_search=False,
            )
        )

        self.assertIn(launched.status, {TaskStatus.CREATED, TaskStatus.PARSED, TaskStatus.PLANNED, TaskStatus.RUNNING})

        deadline = time.time() + 5
        latest = None
        while time.time() < deadline:
            latest = self.service.get_task(launched.id)
            if latest and latest.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                break
            time.sleep(0.05)

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.status, TaskStatus.COMPLETED)
        self.assertGreaterEqual(len(latest.progress_updates), 3)

    def test_cancelled_task_can_resume_from_checkpoint(self) -> None:
        original_run = self.service.executor.run

        def delayed_run(*args, **kwargs):
            time.sleep(0.2)
            return original_run(*args, **kwargs)

        with patch.object(self.service.executor, "run", side_effect=delayed_run):
            launched = self.service.create_task_async(
                TaskCreateRequest(
                    goal="Resume a cancelled task after checkpointing",
                    expected_output="markdown",
                    enable_web_search=False,
                )
            )
            time.sleep(0.05)

            cancelled = self.service.cancel_task(launched.id)
            self.assertIsNotNone(cancelled)
            assert cancelled is not None
            self.assertEqual(cancelled.status, TaskStatus.CANCELLED)
            self.assertTrue(cancelled.checkpoint.resumable)

            resumed = self.service.resume_task(
                launched.id,
                TaskResumeRequest(reason="Continue after manual cancel"),
            )
            self.assertIsNotNone(resumed)

        deadline = time.time() + 5
        latest = resumed
        while time.time() < deadline:
            latest = self.service.get_task(launched.id)
            if latest and latest.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                break
            time.sleep(0.05)

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.status, TaskStatus.COMPLETED)
        self.assertEqual(latest.checkpoint.current_stage, "completed")
        self.assertGreaterEqual(latest.replan_count, 0)

    def test_review_failure_triggers_single_replan_then_completes(self) -> None:
        self.service.reflector.review = Mock(
            side_effect=[
                TaskReview(
                    passed=False,
                    summary="第一次评审发现结构不完整，需要补充。",
                    checklist=["补充结论", "补充步骤说明"],
                ),
                TaskReview(
                    passed=True,
                    summary="修订后通过评审。",
                    checklist=["通过"],
                ),
            ]
        )

        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="生成一个需要修订后再通过的交付结果",
                expected_output="markdown",
                enable_web_search=False,
            )
        )

        self.assertEqual(response.status, TaskStatus.COMPLETED)
        self.assertEqual(response.replan_count, 1)
        self.assertEqual(response.failure_category, FailureCategory.NONE)
        self.assertTrue(any(item.stage == "replanning" for item in response.progress_updates))

    def test_tool_timeout_skips_optional_step_and_completes(self) -> None:
        original_invoke = self.service.tool_registry.invoke

        def invoke_with_timeout(tool_name: str, **kwargs):
            if tool_name == "web_search":
                raise ToolExecutionError("timeout", category=FailureCategory.TOOL_TIMEOUT, retryable=True)
            return original_invoke(tool_name, **kwargs)

        with patch.object(self.service.tool_registry, "invoke", side_effect=invoke_with_timeout):
            response = self.service.create_and_run_task(
                TaskCreateRequest(
                    goal="Research AI agent runtime recovery patterns",
                    expected_output="markdown",
                    enable_web_search=True,
                )
            )

        self.assertEqual(response.status, TaskStatus.COMPLETED)
        self.assertEqual(response.replan_count, 0)
        self.assertEqual(response.checkpoint.last_failure_category, FailureCategory.TOOL_TIMEOUT)
        self.assertEqual(response.checkpoint.last_failure_resolution, FailureResolution.SKIP_FAILED_STEP)
        self.assertEqual(response.checkpoint.last_recovery_step_name, "Web Research")
        self.assertTrue(any(step.status.value == "SKIPPED" for step in response.steps))

    def test_generate_markdown_failure_replans_remaining_steps(self) -> None:
        original_invoke = self.service.tool_registry.invoke
        failures = {"count": 0}

        def invoke_with_render_failure(tool_name: str, **kwargs):
            if tool_name == "generate_markdown" and failures["count"] == 0:
                failures["count"] += 1
                raise ToolExecutionError(
                    "renderer unavailable",
                    category=FailureCategory.TOOL_UNAVAILABLE,
                    retryable=False,
                )
            return original_invoke(tool_name, **kwargs)

        with patch.object(self.service.tool_registry, "invoke", side_effect=invoke_with_render_failure):
            response = self.service.create_and_run_task(
                TaskCreateRequest(
                    goal="Generate a markdown answer with recovery",
                    expected_output="markdown",
                    enable_web_search=False,
                )
            )

        self.assertEqual(response.status, TaskStatus.COMPLETED)
        self.assertEqual(response.replan_count, 1)
        self.assertEqual(response.last_replan_reason, ReplanReason.TOOL_FAILURE)
        self.assertTrue(response.replan_history)
        self.assertEqual(response.replan_history[-1].resume_from_step_name, "Draft Deliverable")
        self.assertEqual(response.checkpoint.last_failure_resolution, FailureResolution.REPLAN_REMAINING_STEPS)
        self.assertEqual(response.checkpoint.last_recovery_step_name, "Draft Deliverable")
        self.assertTrue(any("replan:remaining_from=Draft Deliverable" in note for note in response.context_layers.build_notes))

    def test_internal_error_retries_current_step_then_completes(self) -> None:
        original_run = self.service.executor.run
        run_attempts = {"count": 0}

        def flaky_run(*args, **kwargs):
            if run_attempts["count"] == 0:
                run_attempts["count"] += 1
                raise RuntimeError("temporary execution crash")
            return original_run(*args, **kwargs)

        with patch.object(self.service.executor, "run", side_effect=flaky_run):
            response = self.service.create_and_run_task(
                TaskCreateRequest(
                    goal="Recover from a transient execution failure",
                    expected_output="markdown",
                    enable_web_search=False,
                )
            )

        self.assertEqual(response.status, TaskStatus.COMPLETED)
        self.assertGreaterEqual(response.checkpoint.recovery_attempt, 1)
        self.assertEqual(response.checkpoint.last_failure_category, FailureCategory.INTERNAL_ERROR)
        self.assertEqual(response.checkpoint.last_failure_resolution, FailureResolution.RETRY_CURRENT_STEP)
        self.assertTrue(any(item.stage == "recovery" for item in response.progress_updates))

    def test_source_file_requires_confirmation_before_execution(self) -> None:
        handle, temp_path = tempfile.mkstemp(prefix="confirmation-source-", suffix=".txt", dir=".")
        source_file = Path(temp_path)
        with open(handle, "w", encoding="utf-8", closefd=True) as stream:
            stream.write("needs approval")
        try:
            created = self.service.create_and_run_task(
                TaskCreateRequest(
                    goal="读取本地文件并生成摘要结果",
                    source_path=str(source_file),
                    expected_output="markdown",
                    enable_web_search=False,
                )
            )

            self.assertEqual(created.status, TaskStatus.WAITING_APPROVAL)
            self.assertEqual(len(created.pending_approvals), 1)

            resumed = self.service.confirm_task_action(
                created.id,
                TaskApprovalDecisionRequest(
                    approval_id=created.pending_approvals[0].id,
                    approved=True,
                ),
            )

            deadline = time.time() + 5
            latest = resumed
            while time.time() < deadline:
                latest = self.service.get_task(created.id)
                if latest and latest.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                    break
                time.sleep(0.05)

            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest.status, TaskStatus.COMPLETED)
            self.assertTrue(any(item.stage == "approval" for item in latest.progress_updates))
        finally:
            if source_file.exists():
                source_file.unlink()

    def test_newer_profile_value_archives_older_conflict(self) -> None:
        session = self.service.create_session(SessionCreateRequest(title="画像冲突"))
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="我想学 java，告诉我学习路线",
                expected_output="markdown",
                enable_web_search=False,
                session_id=session.id,
            )
        )
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="我现在更想学 python，请你更新建议",
                expected_output="markdown",
                enable_web_search=False,
                session_id=session.id,
            )
        )

        facts = self.service.list_user_profile_facts(limit=10, include_inactive=True)
        active = [fact for fact in facts if fact.status == UserProfileFactStatus.ACTIVE]
        archived = [fact for fact in facts if fact.status == UserProfileFactStatus.ARCHIVED]

        self.assertTrue(any(fact.value == "Python" for fact in active))
        self.assertTrue(any(fact.value == "Java" for fact in archived))

    def test_manual_profile_edit_affects_future_session_injection(self) -> None:
        first_session = self.service.create_session(SessionCreateRequest(title="手动编辑画像"))
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="我想学 java，告诉我学习路线",
                expected_output="markdown",
                enable_web_search=False,
                session_id=first_session.id,
            )
        )

        facts = self.service.list_user_profile_facts(limit=10, include_inactive=True)
        java_fact = next(fact for fact in facts if fact.value == "Java")

        updated = self.service.update_user_profile_fact(
            java_fact.id,
            UserProfileUpdateRequest(
                value="Python",
                summary="用户手动修正为更偏好 Python。",
            ),
        )

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.value, "Python")
        self.assertEqual(updated.status, UserProfileFactStatus.ACTIVE)

        second_session = self.service.create_session(SessionCreateRequest(title="新会话"))
        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="你知道我最想学哪门语言吗",
                expected_output="markdown",
                enable_web_search=False,
                session_id=second_session.id,
            )
        )

        self.assertTrue(any(hit.value == "Python" for hit in response.profile_hits))

    def test_manual_merge_marks_source_as_merged(self) -> None:
        first = self.service.profile_manager.remember(
            self.service.profile_manager.extract_facts("我想学 java", session_id="s1", task_id="t1")[0]
        )
        second = self.service.profile_manager.remember(
            self.service.profile_manager.extract_facts("我现在更想学 python", session_id="s2", task_id="t2")[0]
        )

        merged = self.service.merge_user_profile_fact(
            first.id,
            UserProfileMergeRequest(
                target_fact_id=second.id,
                summary="保留 Python 作为当前主画像。",
            ),
        )

        self.assertIsNotNone(merged)
        assert merged is not None
        source = self.service.profile_manager.get_fact(first.id)
        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source.status, UserProfileFactStatus.MERGED)
        self.assertEqual(source.superseded_by, second.id)


if __name__ == "__main__":
    unittest.main()

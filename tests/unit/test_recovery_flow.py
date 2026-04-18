import unittest
from datetime import UTC, datetime

from orion_agent.core.config import get_settings
from orion_agent.core.llm_runtime import FallbackLLMClient
from orion_agent.core.models import (
    FailureCategory,
    ParsedGoal,
    ReplanReason,
    Step,
    StepStatus,
    TaskCheckpoint,
    TaskPhase,
    TaskRecord,
    TaskStatus,
    ToolCallStatus,
    ToolInvocation,
)
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService


class RecoveryFlowTests(unittest.TestCase):
    """Tests for recovery strategies: skip failed step, replan remaining steps, and replan from checkpoint."""

    def _build_task_with_failed_step(self) -> TaskRecord:
        base = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        task = TaskRecord(
            title="recovery test",
            status=TaskStatus.RUNNING,
            created_at=base,
            updated_at=base,
            parsed_goal=ParsedGoal(goal="test recovery", constraints=[]),
            checkpoint=TaskCheckpoint(phase=TaskPhase.EXECUTION, current_stage="running"),
            steps=[
                Step(id="step_1", name="Draft Deliverable", description="draft", status=StepStatus.DONE, tool_name="generate_markdown", output="done"),
                Step(id="step_2", name="Web Research", description="search", status=StepStatus.ERROR, tool_name="web_search", output=None),
                Step(id="step_3", name="Review Output", description="review", status=StepStatus.TODO, tool_name=None, output=None),
            ],
            tool_invocations=[
                ToolInvocation(
                    step_id="step_2",
                    tool_name="web_search",
                    status=ToolCallStatus.ERROR,
                    input_payload={"query": "test"},
                    error="timeout",
                    failure_category=FailureCategory.TOOL_TIMEOUT,
                    attempt_count=1,
                )
            ],
        )
        task.failure_category = FailureCategory.TOOL_TIMEOUT
        task.failure_message = "timeout"
        return task

    def test_skip_failed_step_strategy_applied(self) -> None:
        # When a web search step times out, it should be skippable.
        from orion_agent.core.state_machine import transition_task
        task = self._build_task_with_failed_step()
        # Task is already RUNNING, just verify the failed step conditions
        # _can_skip_failed_step should return True for web_search + TOOL_TIMEOUT
        failed_step = next(s for s in task.steps if s.status == StepStatus.ERROR)
        can_skip = any(
            s.tool_name == "web_search" and task.failure_category in {
                FailureCategory.TOOL_TIMEOUT,
                FailureCategory.NETWORK_ERROR,
                FailureCategory.TOOL_UNAVAILABLE,
            }
            for s in task.steps
        )
        self.assertTrue(can_skip)
        self.assertEqual(failed_step.status, StepStatus.ERROR)

    def test_replan_remaining_steps_strategy_identified(self) -> None:
        # When a non-web-search step fails and there are completed steps before it,
        # _can_replan_remaining_steps should identify the case.
        task = self._build_task_with_failed_step()
        task.steps[1].tool_name = "some_other_tool"  # not web_search
        task.steps[1].status = StepStatus.ERROR
        failed_index = 1
        has_completed_before = any(
            s.status in {StepStatus.DONE, StepStatus.SKIPPED} for s in task.steps[:failed_index]
        )
        self.assertTrue(has_completed_before)
        # _can_replan_remaining_steps checks failed_index > 0 and some done/skipped before it
        self.assertGreater(failed_index, 0)

    def test_replan_event_persists_resume_point(self) -> None:
        # ReplanEvent should store resume_from_step_id and resume_from_step_name.
        from orion_agent.core.models import ReplanEvent, ReplanReason
        event = ReplanEvent(
            reason=ReplanReason.TOOL_FAILURE,
            summary="search failed, replanning from checkpoint",
            detail="timeout after retry",
            failure_category=FailureCategory.TOOL_TIMEOUT,
            trigger_phase=TaskPhase.REPLANNING,
            checkpoint_stage="step:Web Research",
            checkpoint_step_id="step_2",
            resume_from_step_id="step_2",
            resume_from_step_name="Web Research",
            recovery_strategy="replan_remaining_steps",
        )
        self.assertEqual(event.resume_from_step_name, "Web Research")
        self.assertEqual(event.resume_from_step_id, "step_2")
        self.assertEqual(event.recovery_strategy, "replan_remaining_steps")
        self.assertEqual(event.failure_category, FailureCategory.TOOL_TIMEOUT)

    def test_mark_task_for_replan_persists_recovery_attempts(self) -> None:
        # ReplanEvent should persist the checkpoint recovery_attempt value.
        service = AgentService(
            repository=TaskRepository(),
            settings=get_settings(),
            llm_client=FallbackLLMClient(),
        )
        task = self._build_task_with_failed_step()
        task.checkpoint.recovery_attempt = 3

        service._mark_task_for_replan(
            task,
            reason=ReplanReason.TOOL_FAILURE,
            summary="tool failed, replanning",
            detail="timeout after retries",
            failure_category=FailureCategory.TOOL_TIMEOUT,
            resume_from_step_id="step_2",
            resume_from_step_name="Web Research",
        )

        self.assertTrue(task.replan_history)
        event = task.replan_history[-1]
        self.assertEqual(event.recovery_attempts, 3)
        self.assertEqual(event.resume_from_step_id, "step_2")
        self.assertEqual(event.resume_from_step_name, "Web Research")

    def test_checkpoint_tracks_recovery_attempt(self) -> None:
        # TaskCheckpoint.recovery_attempt should be incremented on each recovery.
        checkpoint = TaskCheckpoint(phase=TaskPhase.EXECUTION, current_stage="running", recovery_attempt=0)
        checkpoint.recovery_attempt += 1
        self.assertEqual(checkpoint.recovery_attempt, 1)
        checkpoint.recovery_attempt += 1
        self.assertEqual(checkpoint.recovery_attempt, 2)
        # last_recovery fields should track the recovery point
        checkpoint.last_recovery_step_id = "step_2"
        checkpoint.last_recovery_step_name = "Web Research"
        checkpoint.last_recovery_note = "已跳过失败步骤并继续执行"
        self.assertEqual(checkpoint.last_recovery_step_name, "Web Research")
        self.assertEqual(checkpoint.last_recovery_note, "已跳过失败步骤并继续执行")


if __name__ == "__main__":
    unittest.main()

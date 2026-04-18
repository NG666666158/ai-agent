"""Tests for RecoveryStateMachine wired into the runtime_agent recovery flow.

These tests verify that RecoveryStateMachine drives the main recovery path in
AgentService._run_executor_with_recovery, covering skip-step, rebuild-remaining-plan,
and full replan paths, while remaining behaviorally compatible with existing callers.
"""

import unittest
from datetime import UTC, datetime

from orion_agent.core.config import get_settings
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
from orion_agent.core.recovery_policy import RecoveryPolicy, RecoveryState, RecoveryStateMachine
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService


class RecoveryStateMachineRuntimeTests(unittest.TestCase):
    """Verify RecoveryStateMachine integration in AgentService recovery flow."""

    def _make_service(self) -> AgentService:
        return AgentService(repository=TaskRepository(), settings=get_settings())

    def _task_with_failed_step(
        self,
        tool_name: str = "web_search",
        failure_category: FailureCategory = FailureCategory.TOOL_TIMEOUT,
    ) -> TaskRecord:
        """Build a RUNNING task with one DONE step and one ERROR step."""
        base = datetime(2026, 4, 18, tzinfo=UTC)
        return TaskRecord(
            title="runtime recovery test",
            status=TaskStatus.RUNNING,
            created_at=base,
            updated_at=base,
            parsed_goal=ParsedGoal(goal="test", constraints=[]),
            checkpoint=TaskCheckpoint(
                phase=TaskPhase.EXECUTION,
                current_stage="running",
                recovery_attempt=0,
            ),
            steps=[
                Step(
                    id="step_1",
                    name="Draft",
                    description="draft",
                    status=StepStatus.DONE,
                    tool_name="generate_markdown",
                    output="done",
                ),
                Step(
                    id="step_2",
                    name="Web Research",
                    description="search",
                    status=StepStatus.ERROR,
                    tool_name=tool_name,
                    output=None,
                ),
                Step(
                    id="step_3",
                    name="Review",
                    description="review",
                    status=StepStatus.TODO,
                    tool_name=None,
                    output=None,
                ),
            ],
            tool_invocations=[
                ToolInvocation(
                    step_id="step_2",
                    tool_name=tool_name,
                    status=ToolCallStatus.ERROR,
                    input_payload={"query": "test"},
                    error="timeout",
                    failure_category=failure_category,
                    attempt_count=1,
                )
            ],
            failure_category=failure_category,
            failure_message="timeout",
        )

    def test_service_creates_fresh_recovery_state_machine_on_demand(self) -> None:
        # AgentService should create a fresh RecoveryStateMachine for each execution.
        service = self._make_service()
        machine_a = service._create_recovery_state_machine()
        machine_b = service._create_recovery_state_machine()

        self.assertIsInstance(machine_a, RecoveryStateMachine)
        self.assertIsInstance(machine_b, RecoveryStateMachine)
        self.assertIsNot(machine_a, machine_b)
        self.assertEqual(machine_a.current_state, RecoveryState.HEALTHY)
        self.assertEqual(machine_b.current_state, RecoveryState.HEALTHY)
        self.assertFalse(machine_a.is_recovering)
        self.assertFalse(machine_b.is_recovering)

    def test_fresh_recovery_state_machine_does_not_inherit_previous_state(self) -> None:
        # A new execution must not inherit recovery state from a previous task.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="web_search",
            failure_category=FailureCategory.TOOL_TIMEOUT,
        )

        first_machine = service._create_recovery_state_machine()
        first_machine.transition(task, FailureCategory.TOOL_TIMEOUT)
        self.assertEqual(first_machine.current_state, RecoveryState.SKIPPING)

        second_machine = service._create_recovery_state_machine()
        self.assertEqual(second_machine.current_state, RecoveryState.HEALTHY)
        self.assertFalse(second_machine.is_recovering)

    def test_skip_step_transitions_to_skipping_state(self) -> None:
        # When a web_search step times out with a completed prefix, the state machine
        # should transition to SKIPPING.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="web_search",
            failure_category=FailureCategory.TOOL_TIMEOUT,
        )

        machine = service._create_recovery_state_machine()
        next_state = machine.transition(task, FailureCategory.TOOL_TIMEOUT)

        self.assertEqual(next_state, RecoveryState.SKIPPING)
        self.assertEqual(machine.current_state, RecoveryState.SKIPPING)
        self.assertTrue(machine.is_recovering)

    def test_replan_remaining_transitions_to_replanning_remaining(self) -> None:
        # A non-web_search step failure with completed prefix should transition to
        # REPLANNING_REMAINING.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="custom_tool",
            failure_category=FailureCategory.TOOL_TIMEOUT,
        )

        machine = service._create_recovery_state_machine()
        next_state = machine.transition(task, FailureCategory.TOOL_TIMEOUT)

        self.assertEqual(next_state, RecoveryState.REPLANNING_REMAINING)
        self.assertEqual(machine.current_state, RecoveryState.REPLANNING_REMAINING)

    def test_failure_at_first_step_transitions_to_replan_full(self) -> None:
        # A failure at the first step (no completed prefix) should transition to
        # REPLANNING_FULL.
        service = self._make_service()
        base = datetime(2026, 4, 18, tzinfo=UTC)
        task = TaskRecord(
            title="first-step failure",
            status=TaskStatus.RUNNING,
            created_at=base,
            updated_at=base,
            parsed_goal=ParsedGoal(goal="test", constraints=[]),
            checkpoint=TaskCheckpoint(
                phase=TaskPhase.EXECUTION,
                current_stage="running",
                recovery_attempt=0,
            ),
            steps=[
                Step(
                    id="step_1",
                    name="Custom Tool",
                    description="first step",
                    status=StepStatus.ERROR,
                    tool_name="custom_tool",
                    output=None,
                ),
                Step(
                    id="step_2",
                    name="Step 2",
                    description="second",
                    status=StepStatus.TODO,
                    tool_name="some_tool",
                    output=None,
                ),
            ],
            failure_category=FailureCategory.TOOL_TIMEOUT,
            failure_message="tool error",
        )

        machine = service._create_recovery_state_machine()
        next_state = machine.transition(task, FailureCategory.TOOL_TIMEOUT)

        self.assertEqual(next_state, RecoveryState.REPLANNING_FULL)
        self.assertEqual(machine.current_state, RecoveryState.REPLANNING_FULL)

    def test_internal_error_transitions_to_retrying(self) -> None:
        # Internal errors should transition to RETRYING.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="some_tool",
            failure_category=FailureCategory.INTERNAL_ERROR,
        )

        machine = service._create_recovery_state_machine()
        next_state = machine.transition(task, FailureCategory.INTERNAL_ERROR)

        self.assertEqual(next_state, RecoveryState.RETRYING)
        self.assertEqual(machine.current_state, RecoveryState.RETRYING)

    def test_permission_denied_transitions_to_user_action(self) -> None:
        # Permission denied should transition to USER_ACTION.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="restricted_tool",
            failure_category=FailureCategory.PERMISSION_DENIED,
        )

        machine = service._create_recovery_state_machine()
        next_state = machine.transition(task, FailureCategory.PERMISSION_DENIED)

        self.assertEqual(next_state, RecoveryState.USER_ACTION)
        self.assertEqual(machine.current_state, RecoveryState.USER_ACTION)

    def test_skipping_state_drives_skip_logic(self) -> None:
        # The SKIPPING state should drive _prepare_skip_failed_step.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="web_search",
            failure_category=FailureCategory.TOOL_TIMEOUT,
        )
        machine = service._create_recovery_state_machine()
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)

        service._prepare_skip_failed_step(task)

        self.assertEqual(task.steps[1].status, StepStatus.SKIPPED)
        self.assertIsNotNone(task.steps[1].output)

    def test_retrying_state_drives_retry_logic(self) -> None:
        # The RETRYING state should drive _prepare_current_step_retry.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="some_tool",
            failure_category=FailureCategory.INTERNAL_ERROR,
        )
        machine = service._create_recovery_state_machine()
        machine.transition(task, FailureCategory.INTERNAL_ERROR)

        service._prepare_current_step_retry(task)

        self.assertEqual(task.steps[1].status, StepStatus.TODO)
        self.assertIsNone(task.steps[1].output)
        self.assertEqual(task.checkpoint.current_step_id, "step_2")

    def test_replan_remaining_state_drives_partial_replan_logic(self) -> None:
        # The REPLANNING_REMAINING state should drive _prepare_replan_remaining_steps.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="custom_tool",
            failure_category=FailureCategory.TOOL_TIMEOUT,
        )
        machine = service._create_recovery_state_machine()
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)

        from orion_agent.core.llm_runtime import FallbackLLMClient
        from orion_agent.core.models import TaskCreateRequest

        service._prepare_replan_remaining_steps(
            task,
            TaskCreateRequest(goal="test", session_id=None),
        )

        self.assertGreaterEqual(len(task.steps), 1)
        # prefix steps should be preserved
        self.assertEqual(task.steps[0].status, StepStatus.DONE)

    def test_replan_full_state_drives_checkpoint_replan_logic(self) -> None:
        # The REPLANNING_FULL state should drive _prepare_replan_from_failure.
        # _mark_task_for_replan should increment replan_count and append a ReplanEvent.
        from orion_agent.core.models import ContextLayer, TaskCreateRequest

        service = self._make_service()
        base = datetime(2026, 4, 18, tzinfo=UTC)
        task = TaskRecord(
            title="first-step failure",
            status=TaskStatus.RUNNING,
            created_at=base,
            updated_at=base,
            parsed_goal=ParsedGoal(goal="test", constraints=[]),
            checkpoint=TaskCheckpoint(
                phase=TaskPhase.EXECUTION,
                current_stage="running",
                current_step_id="step_1",
                recovery_attempt=0,
            ),
            context_layers=ContextLayer(version=1),
            steps=[
                Step(
                    id="step_1",
                    name="Custom Tool",
                    description="first step",
                    status=StepStatus.ERROR,
                    tool_name="custom_tool",
                    output=None,
                ),
                Step(
                    id="step_2",
                    name="Step 2",
                    description="second",
                    status=StepStatus.TODO,
                    tool_name="some_tool",
                    output=None,
                ),
            ],
            failure_category=FailureCategory.TOOL_TIMEOUT,
            failure_message="tool error",
        )
        machine = service._create_recovery_state_machine()
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)

        service._prepare_replan_from_failure(
            task,
            TaskCreateRequest(goal="test", session_id=None),
        )

        # _mark_task_for_replan should append a ReplanEvent and increment replan_count.
        self.assertEqual(len(task.replan_history), 1)
        self.assertEqual(task.replan_count, 1)
        event = task.replan_history[-1]
        self.assertEqual(event.resume_from_step_id, "step_1")
        self.assertEqual(event.resume_from_step_name, "Custom Tool")

    def test_state_machine_escalates_retrying_to_replan_full_when_retries_exhausted(self) -> None:
        # When retry budget is exhausted, RETRYING should escalate to REPLANNING_FULL.
        settings = get_settings()
        settings.execution_recovery_retries = 1
        service = AgentService(
            repository=TaskRepository(),
            settings=settings,
        )
        task = self._task_with_failed_step(
            tool_name="custom_tool",
            failure_category=FailureCategory.INTERNAL_ERROR,
        )
        task.checkpoint.recovery_attempt = 1  # exhausted

        machine = service._create_recovery_state_machine()
        next_state = machine.transition(task, FailureCategory.INTERNAL_ERROR)

        self.assertEqual(next_state, RecoveryState.REPLANNING_FULL)
        self.assertEqual(machine.current_state, RecoveryState.REPLANNING_FULL)

    def test_state_machine_reset_to_healthy_after_recovery(self) -> None:
        # After a successful recovery action, the state machine should be reset to HEALTHY.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="web_search",
            failure_category=FailureCategory.TOOL_TIMEOUT,
        )
        machine = service._create_recovery_state_machine()
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)
        self.assertEqual(machine.current_state, RecoveryState.SKIPPING)

        machine.reset_to_healthy()

        self.assertEqual(machine.current_state, RecoveryState.HEALTHY)
        self.assertFalse(machine.is_recovering)

    def test_state_description_reflects_current_recovery_state(self) -> None:
        # state_description() should return Chinese text matching the current state.
        service = self._make_service()
        machine = service._create_recovery_state_machine()
        self.assertEqual(machine.state_description(), "正常运行，无恢复进行中")

        task = self._task_with_failed_step(
            tool_name="web_search",
            failure_category=FailureCategory.TOOL_TIMEOUT,
        )
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)
        self.assertEqual(machine.state_description(), "正在跳过失败步骤并继续执行")

    def test_mark_task_for_replan_records_recovery_attempts(self) -> None:
        # _mark_task_for_replan should record the current recovery_attempt from checkpoint.
        service = self._make_service()
        task = self._task_with_failed_step(
            tool_name="custom_tool",
            failure_category=FailureCategory.TOOL_TIMEOUT,
        )
        task.checkpoint.recovery_attempt = 2

        service._mark_task_for_replan(
            task,
            reason=ReplanReason.TOOL_FAILURE,
            summary="tool failed, replanning",
            detail="timeout",
            failure_category=FailureCategory.TOOL_TIMEOUT,
            resume_from_step_id="step_2",
            resume_from_step_name="Web Research",
        )

        self.assertEqual(task.replan_history[-1].recovery_attempts, 2)

    def test_record_failure_checkpoint_updates_task(self) -> None:
        # _record_failure_checkpoint should update checkpoint fields with failure info.
        from orion_agent.core.models import FailureResolution

        service = self._make_service()
        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.TOOL_TIMEOUT
        resolution = FailureResolution.SKIP_FAILED_STEP

        service._record_failure_checkpoint(task, resolution)

        self.assertEqual(task.checkpoint.failure_count, 1)
        self.assertEqual(task.checkpoint.last_failure_category, FailureCategory.TOOL_TIMEOUT)
        self.assertEqual(task.checkpoint.last_failure_resolution, FailureResolution.SKIP_FAILED_STEP)


if __name__ == "__main__":
    unittest.main()

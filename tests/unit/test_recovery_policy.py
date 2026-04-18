import unittest

from orion_agent.core.config import get_settings
from orion_agent.core.models import (
    FailureCategory,
    FailureResolution,
    Step,
    StepStatus,
    TaskRecord,
    TaskStatus,
)
from orion_agent.core.recovery_policy import (
    InvalidTransitionError,
    RecoveryPolicy,
    RecoveryState,
    RecoveryStateMachine,
)


class RecoveryPolicyTests(unittest.TestCase):
    def _make_policy(self) -> RecoveryPolicy:
        return RecoveryPolicy(get_settings())

    def _task_with_step(self, step_status: StepStatus, tool_name: str = "web_search") -> TaskRecord:
        return TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(
                    id="step_1",
                    name="Web Search",
                    description="执行网络搜索",
                    status=step_status,
                    tool_name=tool_name,
                )
            ],
        )

    def test_classify_internal_error_triggers_retry(self) -> None:
        # 场景：内部错误应触发当前步骤重试。
        policy = self._make_policy()
        task = self._task_with_step(StepStatus.ERROR)

        result = policy.classify_failure_resolution(task, FailureCategory.INTERNAL_ERROR)

        self.assertEqual(result, FailureResolution.RETRY_CURRENT_STEP)

    def test_classify_permission_denied_requires_user_action(self) -> None:
        # 场景：权限拒绝需要用户介入。
        policy = self._make_policy()
        task = self._task_with_step(StepStatus.ERROR)

        result = policy.classify_failure_resolution(task, FailureCategory.PERMISSION_DENIED)

        self.assertEqual(result, FailureResolution.REQUIRE_USER_ACTION)

    def test_classify_review_failed_triggers_replan_from_checkpoint(self) -> None:
        # 场景：结果复核失败应从检查点重规划。
        policy = self._make_policy()
        task = self._task_with_step(StepStatus.ERROR)

        result = policy.classify_failure_resolution(task, FailureCategory.REVIEW_FAILED)

        self.assertEqual(result, FailureResolution.REPLAN_FROM_CHECKPOINT)

    def test_classify_web_search_timeout_with_completed_prefix_skips(self) -> None:
        # 场景：web_search 超时且前面已有完成步骤时，应允许跳过失败步骤继续执行。
        policy = self._make_policy()
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Step 1", description="第一步", status=StepStatus.DONE, tool_name="some_tool"),
                Step(id="step_2", name="Web Search", description="网络搜索", status=StepStatus.ERROR, tool_name="web_search"),
                Step(id="step_3", name="Step 3", description="第三步", status=StepStatus.TODO, tool_name="some_tool"),
            ],
        )

        result = policy.classify_failure_resolution(task, FailureCategory.TOOL_TIMEOUT)

        self.assertEqual(result, FailureResolution.SKIP_FAILED_STEP)

    def test_classify_network_error_with_completed_prefix_skips_failed_web_search(self) -> None:
        # 场景：web_search 网络错误且有已完成前缀时，也应允许降级跳过，而不是直接整段重规划。
        policy = self._make_policy()
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Step 1", description="第一步", status=StepStatus.DONE, tool_name="some_tool"),
                Step(id="step_2", name="Web Search", description="网络搜索", status=StepStatus.ERROR, tool_name="web_search"),
                Step(id="step_3", name="Step 3", description="第三步", status=StepStatus.TODO, tool_name="some_tool"),
            ],
        )

        result = policy.classify_failure_resolution(task, FailureCategory.NETWORK_ERROR)

        self.assertEqual(result, FailureResolution.SKIP_FAILED_STEP)

    def test_can_skip_failed_step_true_for_web_search_with_supported_categories(self) -> None:
        # 场景：web_search 在 TOOL_TIMEOUT、NETWORK_ERROR、TOOL_UNAVAILABLE 下都可跳过。
        policy = self._make_policy()
        step = Step(id="s1", name="Web Search", description="网络搜索", status=StepStatus.ERROR, tool_name="web_search")

        self.assertTrue(policy.can_skip_failed_step(step, FailureCategory.TOOL_TIMEOUT))
        self.assertTrue(policy.can_skip_failed_step(step, FailureCategory.NETWORK_ERROR))
        self.assertTrue(policy.can_skip_failed_step(step, FailureCategory.TOOL_UNAVAILABLE))

    def test_can_skip_failed_step_false_for_non_web_search(self) -> None:
        # 场景：非 web_search 工具失败时不允许直接跳过。
        policy = self._make_policy()
        step = Step(id="s1", name="Custom Tool", description="自定义工具", status=StepStatus.ERROR, tool_name="custom_tool")

        self.assertFalse(policy.can_skip_failed_step(step, FailureCategory.TOOL_TIMEOUT))

    def test_can_replan_remaining_steps_true_when_completed_prefix_exists(self) -> None:
        # 场景：失败步骤前存在已完成前缀时，可以只重建后半段计划。
        policy = self._make_policy()
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Step 1", description="第一步", status=StepStatus.DONE, tool_name="some_tool"),
                Step(id="step_2", name="Web Search", description="网络搜索", status=StepStatus.ERROR, tool_name="web_search"),
                Step(id="step_3", name="Step 3", description="第三步", status=StepStatus.TODO, tool_name="some_tool"),
            ],
        )

        self.assertTrue(policy.can_replan_remaining_steps(task, task.steps[1]))

    def test_can_replan_remaining_steps_false_when_no_completed_prefix(self) -> None:
        # 场景：如果失败发生在第一步，前面没有稳定前缀，不允许只重建后半段计划。
        policy = self._make_policy()
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Web Search 1", description="搜索1", status=StepStatus.ERROR, tool_name="web_search"),
                Step(id="step_2", name="Step 2", description="第二步", status=StepStatus.TODO, tool_name="some_tool"),
            ],
        )

        self.assertFalse(policy.can_replan_remaining_steps(task, task.steps[0]))

    def test_classify_network_error_still_skips_for_web_search_without_prefix(self) -> None:
        # 场景：沿用现有生产语义，web_search 的网络错误即使发生在首步，也允许直接跳过降级继续。
        policy = self._make_policy()
        task = self._task_with_step(StepStatus.ERROR)

        result = policy.classify_failure_resolution(task, FailureCategory.NETWORK_ERROR)

        self.assertEqual(result, FailureResolution.SKIP_FAILED_STEP)

    def test_classify_network_error_replans_from_checkpoint_for_non_web_search(self) -> None:
        # 场景：非 web_search 的网络错误不允许跳过，应回退到从检查点重规划。
        policy = self._make_policy()
        task = self._task_with_step(StepStatus.ERROR, tool_name="custom_tool")

        result = policy.classify_failure_resolution(task, FailureCategory.NETWORK_ERROR)

        self.assertEqual(result, FailureResolution.REPLAN_FROM_CHECKPOINT)

    def test_classify_tool_unavailable_triggers_skip_for_web_search(self) -> None:
        # 场景：web_search 工具不可用时，可直接跳过失败步骤。
        policy = self._make_policy()
        task = self._task_with_step(StepStatus.ERROR)

        result = policy.classify_failure_resolution(task, FailureCategory.TOOL_UNAVAILABLE)

        self.assertEqual(result, FailureResolution.SKIP_FAILED_STEP)

    def test_find_failed_step_returns_error_step(self) -> None:
        # 场景：find_failed_step 应返回最近一个 ERROR 状态步骤。
        policy = self._make_policy()
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Step 1", description="第一步", status=StepStatus.DONE, tool_name="some_tool"),
                Step(id="step_2", name="Step 2", description="第二步", status=StepStatus.ERROR, tool_name="some_tool"),
            ],
        )

        result = policy.find_failed_step(task)

        self.assertEqual(result.id, "step_2")


class RecoveryStateMachineTests(unittest.TestCase):
    """Tests for the formal RecoveryStateMachine."""

    def _make_machine(self) -> tuple[RecoveryStateMachine, RecoveryPolicy]:
        policy = RecoveryPolicy(get_settings())
        machine = RecoveryStateMachine(policy, get_settings())
        return machine, policy

    def _task_with_failed_step(self, tool_name: str = "web_search") -> TaskRecord:
        return TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Step 1", description="第一步", status=StepStatus.DONE, tool_name="some_tool"),
                Step(id="step_2", name="Web Search", description="网络搜索", status=StepStatus.ERROR, tool_name=tool_name),
                Step(id="step_3", name="Step 3", description="第三步", status=StepStatus.TODO, tool_name="some_tool"),
            ],
        )

    def test_initial_state_is_healthy(self) -> None:
        # 场景：状态机初始状态应为 HEALTHY。
        machine, _ = self._make_machine()
        self.assertEqual(machine.current_state, RecoveryState.HEALTHY)
        self.assertFalse(machine.is_recovering)

    def test_internal_error_transitions_to_retrying(self) -> None:
        # 场景：内部错误应使状态机转换到 RETRYING 状态。
        machine, policy = self._make_machine()
        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.INTERNAL_ERROR

        next_state = machine.transition(task, FailureCategory.INTERNAL_ERROR)

        self.assertEqual(next_state, RecoveryState.RETRYING)
        self.assertEqual(machine.current_state, RecoveryState.RETRYING)
        self.assertTrue(machine.is_recovering)

    def test_permission_denied_transitions_to_user_action(self) -> None:
        # 场景：权限拒绝应使状态机转换到 USER_ACTION 状态。
        machine, policy = self._make_machine()
        task = self._task_with_failed_step(tool_name="restricted_tool")
        task.failure_category = FailureCategory.PERMISSION_DENIED

        next_state = machine.transition(task, FailureCategory.PERMISSION_DENIED)

        self.assertEqual(next_state, RecoveryState.USER_ACTION)
        self.assertEqual(machine.current_state, RecoveryState.USER_ACTION)

    def test_web_search_timeout_transitions_to_skipping(self) -> None:
        # 场景：web_search 超时且有已完成前缀时，状态机转换到 SKIPPING 状态。
        machine, _ = self._make_machine()
        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.TOOL_TIMEOUT

        next_state = machine.transition(task, FailureCategory.TOOL_TIMEOUT)

        self.assertEqual(next_state, RecoveryState.SKIPPING)
        self.assertEqual(machine.current_state, RecoveryState.SKIPPING)

    def test_non_web_search_failure_at_first_step_transitions_to_replan_full(self) -> None:
        # 场景：非 web_search 工具在第一步失败（无已完成前缀）时，无法做 partial replan，
        # 故转换到 REPLANNING_FULL 状态。
        machine, _ = self._make_machine()
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Custom Tool", description="自定义工具", status=StepStatus.ERROR, tool_name="custom_tool"),
                Step(id="step_2", name="Step 2", description="第二步", status=StepStatus.TODO, tool_name="some_tool"),
            ],
        )
        task.failure_category = FailureCategory.TOOL_TIMEOUT

        next_state = machine.transition(task, FailureCategory.TOOL_TIMEOUT)

        # can_replan_remaining_steps returns False because failed_index=0 (no prefix)
        self.assertEqual(next_state, RecoveryState.REPLANNING_FULL)
        self.assertEqual(machine.current_state, RecoveryState.REPLANNING_FULL)

    def test_input_error_transitions_to_fail_fast(self) -> None:
        # 场景：INPUT_ERROR 属于无法恢复的错误类型，应直接转换到 FAILED（终端状态）。
        machine, _ = self._make_machine()
        # Use a single-step task so can_replan_remaining_steps returns False
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Some Tool", description="工具", status=StepStatus.ERROR, tool_name="some_tool"),
            ],
        )
        task.failure_category = FailureCategory.INPUT_ERROR

        next_state = machine.transition(task, FailureCategory.INPUT_ERROR)

        # INPUT_ERROR falls through to FAIL_FAST
        self.assertEqual(next_state, RecoveryState.FAILED)
        self.assertEqual(machine.current_state, RecoveryState.FAILED)

    def test_failed_state_is_terminal(self) -> None:
        # 场景：FAILED 是终端状态，不能再转换到其他状态。
        machine, _ = self._make_machine()
        # Use a single-step task so can_replan_remaining_steps returns False
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Some Tool", description="工具", status=StepStatus.ERROR, tool_name="some_tool"),
            ],
        )
        task.failure_category = FailureCategory.INPUT_ERROR
        machine.transition(task, FailureCategory.INPUT_ERROR)  # enters FAILED

        self.assertFalse(machine.can_transition_to(RecoveryState.HEALTHY))
        self.assertFalse(machine.can_transition_to(RecoveryState.RETRYING))
        self.assertFalse(machine.can_transition_to(RecoveryState.SKIPPING))

    def test_retrying_can_escalate_to_skipping(self) -> None:
        # 场景：RETRYING 状态下若再次失败且策略判断可跳过，状态机可 escalation 到 SKIPPING。
        # 这是有效的降级路径：重试失败后降级跳过。
        machine, _ = self._make_machine()
        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.INTERNAL_ERROR
        machine.transition(task, FailureCategory.INTERNAL_ERROR)  # enters RETRYING

        # From RETRYING, escalation to SKIPPING is valid (retry failed, try skip)
        self.assertTrue(machine.can_transition_to(RecoveryState.SKIPPING))
        self.assertTrue(machine.can_transition_to(RecoveryState.REPLANNING_FULL))

    def test_retrying_can_escalate_to_replanning_full(self) -> None:
        # 场景：RETRYING 状态下可以 escalation 到 REPLANNING_FULL。
        machine, _ = self._make_machine()
        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.INTERNAL_ERROR
        machine.transition(task, FailureCategory.INTERNAL_ERROR)  # enters RETRYING

        self.assertTrue(machine.can_transition_to(RecoveryState.REPLANNING_FULL))
        self.assertTrue(machine.can_transition_to(RecoveryState.FAILED))

    def test_skipping_transitions_to_healthy_on_success(self) -> None:
        # 场景：SKIPPING 成功后可以返回 HEALTHY。
        machine, _ = self._make_machine()
        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.TOOL_TIMEOUT
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)  # enters SKIPPING

        self.assertTrue(machine.can_transition_to(RecoveryState.HEALTHY))

    def test_skipping_can_escalate_to_replan_remaining(self) -> None:
        # 场景：SKIPPING 状态下再次失败可以 escalation 到 REPLANNING_REMAINING。
        machine, _ = self._make_machine()
        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.TOOL_TIMEOUT
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)  # enters SKIPPING

        self.assertTrue(machine.can_transition_to(RecoveryState.REPLANNING_REMAINING))
        self.assertTrue(machine.can_transition_to(RecoveryState.REPLANNING_FULL))
        self.assertTrue(machine.can_transition_to(RecoveryState.FAILED))

    def test_replan_remaining_transitions_to_healthy_or_failed(self) -> None:
        # 场景：REPLANNING_REMAINING 只能转换到 HEALTHY 或 FAILED。
        machine, _ = self._make_machine()
        task = self._task_with_failed_step(tool_name="custom_tool")
        task.failure_category = FailureCategory.TOOL_TIMEOUT
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)  # enters REPLANNING_FULL

        self.assertTrue(machine.can_transition_to(RecoveryState.HEALTHY))
        self.assertTrue(machine.can_transition_to(RecoveryState.FAILED))
        self.assertFalse(machine.can_transition_to(RecoveryState.RETRYING))
        self.assertFalse(machine.can_transition_to(RecoveryState.SKIPPING))
        self.assertFalse(machine.can_transition_to(RecoveryState.USER_ACTION))

    def test_user_action_transitions_to_healthy_or_failed(self) -> None:
        # 场景：USER_ACTION 只能转换到 HEALTHY（用户批准）或 FAILED（用户拒绝）。
        machine, _ = self._make_machine()
        task = self._task_with_failed_step(tool_name="restricted_tool")
        task.failure_category = FailureCategory.PERMISSION_DENIED
        machine.transition(task, FailureCategory.PERMISSION_DENIED)  # enters USER_ACTION

        self.assertTrue(machine.can_transition_to(RecoveryState.HEALTHY))
        self.assertTrue(machine.can_transition_to(RecoveryState.FAILED))
        self.assertFalse(machine.can_transition_to(RecoveryState.RETRYING))
        self.assertFalse(machine.can_transition_to(RecoveryState.SKIPPING))

    def test_reset_to_healthy(self) -> None:
        # 场景：成功恢复后可以重置到 HEALTHY 状态。
        machine, _ = self._make_machine()
        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.TOOL_TIMEOUT
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)  # enters SKIPPING

        machine.reset_to_healthy()

        self.assertEqual(machine.current_state, RecoveryState.HEALTHY)
        self.assertFalse(machine.is_recovering)

    def test_state_description(self) -> None:
        # 场景：state_description 返回当前状态的中文描述。
        machine, _ = self._make_machine()
        self.assertEqual(machine.state_description(), "正常运行，无恢复进行中")

        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.TOOL_TIMEOUT
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)
        self.assertEqual(machine.state_description(), "正在跳过失败步骤并继续执行")

    def test_resolution_to_state_mapping(self) -> None:
        # 场景：各种 FailureResolution 应正确映射到对应的 RecoveryState。
        machine, _ = self._make_machine()

        self.assertEqual(
            machine._resolution_to_state(FailureResolution.RETRY_CURRENT_STEP),
            RecoveryState.RETRYING,
        )
        self.assertEqual(
            machine._resolution_to_state(FailureResolution.SKIP_FAILED_STEP),
            RecoveryState.SKIPPING,
        )
        self.assertEqual(
            machine._resolution_to_state(FailureResolution.REPLAN_REMAINING_STEPS),
            RecoveryState.REPLANNING_REMAINING,
        )
        self.assertEqual(
            machine._resolution_to_state(FailureResolution.REPLAN_FROM_CHECKPOINT),
            RecoveryState.REPLANNING_FULL,
        )
        self.assertEqual(
            machine._resolution_to_state(FailureResolution.REQUIRE_USER_ACTION),
            RecoveryState.USER_ACTION,
        )
        self.assertEqual(
            machine._resolution_to_state(FailureResolution.FAIL_FAST),
            RecoveryState.FAILED,
        )

    def test_is_recovering(self) -> None:
        # 场景：is_recovering 在非 HEALTHY、非 FAILED 状态时返回 True。
        machine, _ = self._make_machine()
        self.assertFalse(machine.is_recovering)

        task = self._task_with_failed_step()
        task.failure_category = FailureCategory.TOOL_TIMEOUT
        machine.transition(task, FailureCategory.TOOL_TIMEOUT)  # SKIPPING
        self.assertTrue(machine.is_recovering)

        machine.reset_to_healthy()
        self.assertFalse(machine.is_recovering)


if __name__ == "__main__":
    unittest.main()

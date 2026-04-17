import unittest

from orion_agent.core.config import Settings, get_settings
from orion_agent.core.models import (
    FailureCategory,
    FailureResolution,
    Step,
    StepStatus,
    TaskRecord,
    TaskStatus,
)
from orion_agent.core.recovery_policy import RecoveryPolicy


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
        # 场景：评审失败从头重规划。
        policy = self._make_policy()
        task = self._task_with_step(StepStatus.ERROR)

        result = policy.classify_failure_resolution(task, FailureCategory.REVIEW_FAILED)

        self.assertEqual(result, FailureResolution.REPLAN_FROM_CHECKPOINT)

    def test_classify_web_search_timeout_with_completed_prefix_skips(self) -> None:
        # 场景：web_search 超时时，若有已完成的前置步骤则跳过该步骤。
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

    def test_can_skip_failed_step_true_for_web_search_with_tool_timeout(self) -> None:
        # 场景：web_search + TOOL_TIMEOUT 可以跳过。
        policy = self._make_policy()
        step = Step(id="s1", name="Web Search", description="网络搜索", status=StepStatus.ERROR, tool_name="web_search")

        self.assertTrue(policy.can_skip_failed_step(step, FailureCategory.TOOL_TIMEOUT))
        self.assertTrue(policy.can_skip_failed_step(step, FailureCategory.TOOL_UNAVAILABLE))

    def test_can_skip_failed_step_false_for_non_web_search(self) -> None:
        # 场景：非 web_search 工具的失败不能跳过。
        policy = self._make_policy()
        step = Step(id="s1", name="Custom Tool", description="自定义工具", status=StepStatus.ERROR, tool_name="custom_tool")

        self.assertFalse(policy.can_skip_failed_step(step, FailureCategory.TOOL_TIMEOUT))

    def test_can_replan_remaining_steps_true_when_completed_prefix_exists(self) -> None:
        # 场景：若失败步骤前有已完成步骤，则可以重规划剩余步骤。
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
        failed_step = task.steps[1]

        self.assertTrue(policy.can_replan_remaining_steps(task, failed_step))

    def test_can_replan_remaining_steps_false_when_no_completed_prefix(self) -> None:
        # 场景：若失败步骤前没有已完成步骤，不能重规划剩余步骤。
        policy = self._make_policy()
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Web Search 1", description="搜索1", status=StepStatus.ERROR, tool_name="web_search"),
                Step(id="step_2", name="Step 2", description="第二步", status=StepStatus.TODO, tool_name="some_tool"),
            ],
        )
        failed_step = task.steps[0]

        self.assertFalse(policy.can_replan_remaining_steps(task, failed_step))

    def test_classify_network_error_triggers_replan_from_checkpoint(self) -> None:
        # 场景：网络错误触发从头重规划。
        policy = self._make_policy()
        task = self._task_with_step(StepStatus.ERROR)

        result = policy.classify_failure_resolution(task, FailureCategory.NETWORK_ERROR)

        self.assertEqual(result, FailureResolution.REPLAN_FROM_CHECKPOINT)

    def test_classify_tool_unavailable_triggers_skip_for_web_search(self) -> None:
        # 场景：web_search + 工具不可用触发跳过步骤（因 can_skip 返回 True）。
        policy = self._make_policy()
        task = self._task_with_step(StepStatus.ERROR)

        result = policy.classify_failure_resolution(task, FailureCategory.TOOL_UNAVAILABLE)

        self.assertEqual(result, FailureResolution.SKIP_FAILED_STEP)

    def test_find_failed_step_returns_error_step(self) -> None:
        # 场景：_find_failed_step 返回状态为 ERROR 的步骤（逆序搜索）。
        policy = self._make_policy()
        task = TaskRecord(
            title="test",
            status=TaskStatus.RUNNING,
            steps=[
                Step(id="step_1", name="Step 1", description="第一步", status=StepStatus.DONE, tool_name="some_tool"),
                Step(id="step_2", name="Step 2", description="第二步", status=StepStatus.ERROR, tool_name="some_tool"),
            ],
        )

        result = policy._find_failed_step(task)

        self.assertEqual(result.id, "step_2")


if __name__ == "__main__":
    unittest.main()
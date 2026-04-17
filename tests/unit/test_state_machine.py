import unittest

from orion_agent.core.models import TaskRecord, TaskStatus
from orion_agent.core.state_machine import InvalidTaskTransition, transition_task


class StateMachineTests(unittest.TestCase):
    def test_valid_state_transition_updates_status_and_timestamp(self) -> None:
        task = TaskRecord(title="state transition")
        before = task.updated_at
        transition_task(task, TaskStatus.PARSED)
        self.assertEqual(task.status, TaskStatus.PARSED)
        self.assertGreaterEqual(task.updated_at, before)

    def test_invalid_state_transition_raises_exception(self) -> None:
        task = TaskRecord(title="state invalid")
        with self.assertRaises(InvalidTaskTransition):
            transition_task(task, TaskStatus.RUNNING)

    def test_terminal_states_do_not_allow_further_transition(self) -> None:
        task = TaskRecord(title="state terminal", status=TaskStatus.COMPLETED)
        with self.assertRaises(InvalidTaskTransition):
            transition_task(task, TaskStatus.RUNNING)

    def test_cancelled_task_can_resume_to_running(self) -> None:
        task = TaskRecord(title="state cancelled", status=TaskStatus.CANCELLED)
        transition_task(task, TaskStatus.RUNNING)
        self.assertEqual(task.status, TaskStatus.RUNNING)

    def test_failed_task_can_resume_to_running(self) -> None:
        task = TaskRecord(title="state failed", status=TaskStatus.FAILED)
        transition_task(task, TaskStatus.RUNNING)
        self.assertEqual(task.status, TaskStatus.RUNNING)

    def test_running_waiting_tool_roundtrip_is_valid(self) -> None:
        task = TaskRecord(title="state tool wait", status=TaskStatus.RUNNING)
        transition_task(task, TaskStatus.WAITING_TOOL)
        self.assertEqual(task.status, TaskStatus.WAITING_TOOL)
        transition_task(task, TaskStatus.RUNNING)
        self.assertEqual(task.status, TaskStatus.RUNNING)

    def test_running_replanning_roundtrip_is_valid(self) -> None:
        task = TaskRecord(title="state replanning", status=TaskStatus.RUNNING)
        transition_task(task, TaskStatus.REPLANNING)
        self.assertEqual(task.status, TaskStatus.REPLANNING)
        transition_task(task, TaskStatus.RUNNING)
        self.assertEqual(task.status, TaskStatus.RUNNING)

    def test_planned_waiting_approval_roundtrip_is_valid(self) -> None:
        task = TaskRecord(title="state approval", status=TaskStatus.PLANNED)
        transition_task(task, TaskStatus.WAITING_APPROVAL)
        self.assertEqual(task.status, TaskStatus.WAITING_APPROVAL)
        transition_task(task, TaskStatus.RUNNING)
        self.assertEqual(task.status, TaskStatus.RUNNING)

    def test_reflecting_cannot_jump_to_waiting_tool(self) -> None:
        task = TaskRecord(title="reflecting state", status=TaskStatus.REFLECTING)
        with self.assertRaises(InvalidTaskTransition):
            transition_task(task, TaskStatus.WAITING_TOOL)


if __name__ == "__main__":
    unittest.main()

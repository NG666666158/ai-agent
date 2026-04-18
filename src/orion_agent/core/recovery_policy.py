"""Dedicated recovery policy for Orion Agent."""

from __future__ import annotations

from dataclasses import dataclass

from orion_agent.core.config import Settings
from orion_agent.core.models import FailureCategory, FailureResolution, Step, StepStatus, TaskRecord


@dataclass
class RecoveryPolicy:
    """Encapsulates failure recovery decision logic."""

    settings: Settings

    def classify_failure_resolution(self, task: TaskRecord, category: FailureCategory) -> FailureResolution:
        """Classify how to handle a failure given its category."""
        failed_step = self.find_failed_step(task)
        if category == FailureCategory.INTERNAL_ERROR:
            return FailureResolution.RETRY_CURRENT_STEP
        if category == FailureCategory.PERMISSION_DENIED:
            return FailureResolution.REQUIRE_USER_ACTION
        if category == FailureCategory.REVIEW_FAILED:
            return FailureResolution.REPLAN_FROM_CHECKPOINT
        if failed_step and self.can_skip_failed_step(failed_step, category):
            return FailureResolution.SKIP_FAILED_STEP
        if failed_step and self.can_replan_remaining_steps(task, failed_step):
            return FailureResolution.REPLAN_REMAINING_STEPS
        if category in {FailureCategory.TOOL_TIMEOUT, FailureCategory.NETWORK_ERROR, FailureCategory.TOOL_UNAVAILABLE}:
            return FailureResolution.REPLAN_FROM_CHECKPOINT
        return FailureResolution.FAIL_FAST

    def can_skip_failed_step(self, failed_step: Step, category: FailureCategory) -> bool:
        """Determine if a failed step can be safely skipped."""
        return failed_step.tool_name == "web_search" and category in {
            FailureCategory.TOOL_TIMEOUT,
            FailureCategory.NETWORK_ERROR,
            FailureCategory.TOOL_UNAVAILABLE,
        }

    def can_replan_remaining_steps(self, task: TaskRecord, failed_step: Step) -> bool:
        """Determine if only the remaining suffix should be rebuilt."""
        try:
            failed_index = next(index for index, step in enumerate(task.steps) if step.id == failed_step.id)
        except StopIteration:
            return False
        return failed_index > 0 and any(
            step.status in {StepStatus.DONE, StepStatus.SKIPPED}
            for step in task.steps[:failed_index]
        )

    def find_failed_step(self, task: TaskRecord) -> Step | None:
        """Return the most recent failed step from the execution plan."""
        for step in reversed(task.steps):
            if step.status == StepStatus.ERROR:
                return step
        return None

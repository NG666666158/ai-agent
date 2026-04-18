"""Dedicated recovery policy for Orion Agent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from orion_agent.core.config import Settings
from orion_agent.core.models import FailureCategory, FailureResolution, Step, StepStatus, TaskRecord


class RecoveryState(str, Enum):
    """Formal recovery states for the state machine.

    States:
        HEALTHY: Normal execution, no recovery in progress.
        RETRYING: Retrying the current failed step.
        SKIPPING: Skipping a failed step and continuing.
        REPLANNING_REMAINING: Rebuilding only the suffix after a failed step.
        REPLANNING_FULL: Full replan from the last checkpoint.
        USER_ACTION: Waiting for user to approve or provide input.
        FAILED: Recovery exhausted, task has failed permanently.

    Transition Rules:
        HEALTHY can transition to any active recovery state (RETRYING, SKIPPING,
            REPLANNING_REMAINING, REPLANNING_FULL, USER_ACTION) or directly to FAILED.
        RETRYING can go to HEALTHY (on success), or escalate to SKIPPING,
            REPLANNING_REMAINING, REPLANNING_FULL, or FAILED.
        SKIPPING transitions to HEALTHY on success, or escalates to REPLANNING_* or FAILED.
        REPLANNING_* transitions to HEALTHY on success, or FAILED on exhaust.
        USER_ACTION goes to HEALTHY on success, or FAILED on deny/timeout.
        FAILED is terminal — no transitions allowed.
    """

    HEALTHY = "HEALTHY"
    RETRYING = "RETRYING"
    SKIPPING = "SKIPPING"
    REPLANNING_REMAINING = "REPLANNING_REMAINING"
    REPLANNING_FULL = "REPLANNING_FULL"
    USER_ACTION = "USER_ACTION"
    FAILED = "FAILED"


class InvalidTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""

    pass


class MaxRetriesExceeded(Exception):
    """Raised when recovery attempts exceed configured limits."""

    pass


# Explicit state transition map. Each state maps to the set of states it can legally transition to.
_RECOVERY_STATE_TRANSITIONS: dict[RecoveryState, set[RecoveryState]] = {
    RecoveryState.HEALTHY: {
        RecoveryState.RETRYING,
        RecoveryState.SKIPPING,
        RecoveryState.REPLANNING_REMAINING,
        RecoveryState.REPLANNING_FULL,
        RecoveryState.USER_ACTION,
        RecoveryState.FAILED,
    },
    RecoveryState.RETRYING: {
        RecoveryState.HEALTHY,
        RecoveryState.SKIPPING,
        RecoveryState.REPLANNING_REMAINING,
        RecoveryState.REPLANNING_FULL,
        RecoveryState.FAILED,
    },
    RecoveryState.SKIPPING: {
        RecoveryState.HEALTHY,
        RecoveryState.REPLANNING_REMAINING,
        RecoveryState.REPLANNING_FULL,
        RecoveryState.FAILED,
    },
    RecoveryState.REPLANNING_REMAINING: {
        RecoveryState.HEALTHY,
        RecoveryState.FAILED,
    },
    RecoveryState.REPLANNING_FULL: {
        RecoveryState.HEALTHY,
        RecoveryState.FAILED,
    },
    RecoveryState.USER_ACTION: {
        RecoveryState.HEALTHY,
        RecoveryState.FAILED,
    },
    RecoveryState.FAILED: set(),  # Terminal state — no exits.
}


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


class RecoveryStateMachine:
    """Formal state machine for recovery transitions.

    Encapsulates the full recovery state lifecycle with explicit, validated
    transitions. Replaces ad-hoc if/else recovery chains in runtime_agent with
    a single source of truth for recovery state progression.

    Skip-step behavior (SKIPPING):
        Allowed when: failed step is web_search AND failure category is
        TOOL_TIMEOUT, NETWORK_ERROR, or TOOL_UNAVAILABLE.
        Effect: failed step marked SKIPPED, execution continues with next step.
        Escalation: on further failure, transitions to REPLANNING_* or FAILED.

    Rebuild-remaining-plan behavior (REPLANNING_REMAINING):
        Allowed when: failed step has a non-empty completed prefix
        (i.e., failed_index > 0 and at least one DONE/SKIPPED step before it).
        Effect: prefix steps preserved, suffix rebuilt from scratch.
        Escalation: on further failure, transitions to REPLANNING_FULL or FAILED.

    Full replan behavior (REPLANNING_FULL):
        Allowed when: any failure that doesn't qualify for skip or partial replan.
        Effect: entire plan discarded, rebuilt from last checkpoint.
        Escalation: on exhaust, transitions to FAILED.

    Usage:
        machine = RecoveryStateMachine(recovery_policy, settings)
        next_state = machine.transition(task, failure_category)
        if machine.can_retry():
            machine.increment_retry()
    """

    _policy: RecoveryPolicy
    _settings: Settings
    _current_state: RecoveryState

    def __init__(self, policy: RecoveryPolicy, settings: Settings) -> None:
        self._policy = policy
        self._settings = settings
        self._current_state = RecoveryState.HEALTHY

    @property
    def current_state(self) -> RecoveryState:
        """Return the current recovery state."""
        return self._current_state

    @property
    def is_recovering(self) -> bool:
        """Return True if a recovery action is in progress (non-HEALTHY, non-FAILED)."""
        return self._current_state not in {RecoveryState.HEALTHY, RecoveryState.FAILED}

    def can_transition_to(self, target: RecoveryState) -> bool:
        """Return True if transition from current state to target is legal."""
        if self._current_state == RecoveryState.FAILED:
            return False
        return target in _RECOVERY_STATE_TRANSITIONS.get(self._current_state, set())

    def transition(self, task: TaskRecord, category: FailureCategory) -> RecoveryState:
        """Determine and execute the next recovery state transition.

        Uses the embedded RecoveryPolicy to classify the failure, maps the
        resolution to a formal RecoveryState, validates the transition is
        legal, and updates internal state.

        Raises:
            InvalidTransitionError: if the computed transition is not legal.
            MaxRetriesExceeded: if retry limit is exceeded.
        """
        if self._current_state == RecoveryState.FAILED:
            raise InvalidTransitionError("Cannot transition from terminal FAILED state")

        resolution = self._policy.classify_failure_resolution(task, category)

        next_state = self._resolution_to_state(resolution)
        if next_state == RecoveryState.RETRYING and not self.can_retry(task):
            # Exhausted retry budget — escalate to full replan
            next_state = RecoveryState.REPLANNING_FULL

        if not self.can_transition_to(next_state):
            raise InvalidTransitionError(
                f"Illegal recovery transition from {self._current_state.value} to {next_state.value}"
            )

        self._current_state = next_state
        return next_state

    def reset_to_healthy(self) -> None:
        """Reset state machine to HEALTHY after successful recovery."""
        self._current_state = RecoveryState.HEALTHY

    def can_retry(self, task: TaskRecord | None = None) -> bool:
        """Return True if retry attempts remain within the configured limit."""
        if task is None:
            return self._settings.execution_recovery_retries > 0
        return task.checkpoint.recovery_attempt < self._settings.execution_recovery_retries

    def _resolution_to_state(self, resolution: FailureResolution) -> RecoveryState:
        """Map a FailureResolution to the corresponding RecoveryState."""
        return {
            FailureResolution.RETRY_CURRENT_STEP: RecoveryState.RETRYING,
            FailureResolution.SKIP_FAILED_STEP: RecoveryState.SKIPPING,
            FailureResolution.REPLAN_REMAINING_STEPS: RecoveryState.REPLANNING_REMAINING,
            FailureResolution.REPLAN_FROM_CHECKPOINT: RecoveryState.REPLANNING_FULL,
            FailureResolution.REQUIRE_USER_ACTION: RecoveryState.USER_ACTION,
            FailureResolution.FAIL_FAST: RecoveryState.FAILED,
        }.get(resolution, RecoveryState.FAILED)

    def state_description(self) -> str:
        """Return a human-readable description of the current state and its implications."""
        descriptions = {
            RecoveryState.HEALTHY: "正常运行，无恢复进行中",
            RecoveryState.RETRYING: "正在重试当前失败步骤",
            RecoveryState.SKIPPING: "正在跳过失败步骤并继续执行",
            RecoveryState.REPLANNING_REMAINING: "正在重建失败步骤之后的计划",
            RecoveryState.REPLANNING_FULL: "正在从检查点重建完整计划",
            RecoveryState.USER_ACTION: "正在等待用户授权或输入",
            RecoveryState.FAILED: "恢复失败，任务已终止",
        }
        return descriptions.get(self._current_state, "未知状态")

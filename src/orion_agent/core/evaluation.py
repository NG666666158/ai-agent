from __future__ import annotations

from dataclasses import dataclass

from orion_agent.core.models import TaskResponse


@dataclass(slots=True)
class EvaluationResult:
    score: float
    checks: list[str]


class TaskEvaluator:
    def evaluate(self, task: TaskResponse) -> EvaluationResult:
        checks: list[tuple[str, bool]] = [
            ("task completed", task.status.value == "COMPLETED"),
            ("has steps", len(task.steps) >= 4),
            ("has result", bool(task.result and task.result.strip())),
            ("has review", task.review is not None and task.review.passed),
            ("has tool traces", len(task.tool_invocations) >= 1),
        ]
        score = sum(1 for _, passed in checks if passed) / len(checks)
        return EvaluationResult(
            score=score,
            checks=[f"{name}: {'pass' if passed else 'fail'}" for name, passed in checks],
        )

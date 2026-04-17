"""ExecutionRegistry for Orion Agent.

Provides a centralized registry of execution stage metadata so that
execution definitions are shared across runtime, recovery, and UI rendering.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionStage:
    """Metadata for a single execution stage kind."""

    kind: str
    title: str
    short_label: str  # Chinese display label for frontend


# Registry of all known execution stages.
# - kind: the canonical stage identifier used in ExecutionNode.kind
# - title: full descriptive title (used in ExecutionNode.title)
# - short_label: brief Chinese label for UI display
EXECUTION_STAGES: dict[str, ExecutionStage] = {
    "query_rewrite": ExecutionStage(
        kind="query_rewrite",
        title="Query 改写与任务标准化",
        short_label="Query 改写",
    ),
    "prompt_assembly": ExecutionStage(
        kind="prompt_assembly",
        title="上下文分层与 Prompt 拼接",
        short_label="Prompt 拼接",
    ),
    "vector_retrieval": ExecutionStage(
        kind="vector_retrieval",
        title="向量检索与语义召回",
        short_label="向量检索",
    ),
    "multi_recall": ExecutionStage(
        kind="multi_recall",
        title="多路召回与来源整合",
        short_label="多路召回",
    ),
    "progress": ExecutionStage(
        kind="progress",
        title="系统进度",
        short_label="系统进度",
    ),
    "step": ExecutionStage(
        kind="step",
        title="执行步骤",
        short_label="执行步骤",
    ),
    "tool": ExecutionStage(
        kind="tool",
        title="工具调用",
        short_label="工具调用",
    ),
    "recovery": ExecutionStage(
        kind="recovery",
        title="恢复与重规划",
        short_label="恢复与重规划",
    ),
    "answer_generation": ExecutionStage(
        kind="answer_generation",
        title="最终回答生成",
        short_label="回答生成",
    ),
    "review": ExecutionStage(
        kind="review",
        title="结果复核",
        short_label="结果复核",
    ),
}


def get_stage(kind: str) -> ExecutionStage | None:
    """Return the ExecutionStage for a given kind, or None if unknown."""
    return EXECUTION_STAGES.get(kind)


def stage_title(kind: str, default: str | None = None) -> str:
    """Return the title for a stage kind, or default if not found."""
    stage = EXECUTION_STAGES.get(kind)
    return stage.title if stage else (default or kind)


def stage_short_label(kind: str, default: str | None = None) -> str:
    """Return the short Chinese label for a stage kind, or default if not found."""
    stage = EXECUTION_STAGES.get(kind)
    return stage.short_label if stage else (default or kind)
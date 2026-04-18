"""Execution stage registry for Orion Agent.

Centralizes stage metadata so runtime recovery, execution timeline rendering,
and frontend labels share one source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionStage:
    """Metadata for a single execution stage kind."""

    kind: str
    title: str
    short_label: str
    category: str
    sort_order: int
    supports_artifacts: bool = True


EXECUTION_STAGES: dict[str, ExecutionStage] = {
    "thinking": ExecutionStage(
        kind="thinking",
        title="输入解析与任务标准化",
        short_label="输入解析",
        category="reasoning",
        sort_order=5,
    ),
    "query_rewrite": ExecutionStage(
        kind="query_rewrite",
        title="输入解析与任务标准化",
        short_label="任务解析",
        category="reasoning",
        sort_order=10,
    ),
    "context": ExecutionStage(
        kind="context",
        title="上下文分层与提示词拼接",
        short_label="上下文加载",
        category="reasoning",
        sort_order=15,
    ),
    "prompt_assembly": ExecutionStage(
        kind="prompt_assembly",
        title="上下文分层与提示词拼接",
        short_label="上下文组装",
        category="reasoning",
        sort_order=20,
    ),
    "vector_retrieval": ExecutionStage(
        kind="vector_retrieval",
        title="向量检索与语义召回",
        short_label="向量召回",
        category="retrieval",
        sort_order=30,
    ),
    "memory": ExecutionStage(
        kind="memory",
        title="多路召回与来源整合",
        short_label="记忆召回",
        category="retrieval",
        sort_order=45,
    ),
    "multi_recall": ExecutionStage(
        kind="multi_recall",
        title="多路召回与来源整合",
        short_label="多路召回",
        category="retrieval",
        sort_order=50,
    ),
    "planning": ExecutionStage(
        kind="planning",
        title="执行计划生成",
        short_label="计划生成",
        category="reasoning",
        sort_order=55,
    ),
    "step": ExecutionStage(
        kind="step",
        title="执行步骤",
        short_label="执行步骤",
        category="runtime",
        sort_order=60,
    ),
    "running": ExecutionStage(
        kind="running",
        title="任务执行中",
        short_label="执行中",
        category="runtime",
        sort_order=62,
    ),
    "tool": ExecutionStage(
        kind="tool",
        title="工具调用",
        short_label="工具调用",
        category="runtime",
        sort_order=70,
    ),
    "approval": ExecutionStage(
        kind="approval",
        title="等待用户确认",
        short_label="待确认",
        category="runtime",
        sort_order=73,
    ),
    "recovery": ExecutionStage(
        kind="recovery",
        title="恢复与重规划",
        short_label="恢复与重规划",
        category="recovery",
        sort_order=80,
    ),
    "replanning": ExecutionStage(
        kind="replanning",
        title="恢复与重规划",
        short_label="重规划",
        category="recovery",
        sort_order=82,
    ),
    "answer_generation": ExecutionStage(
        kind="answer_generation",
        title="回答生成",
        short_label="回答生成",
        category="output",
        sort_order=90,
    ),
    "review": ExecutionStage(
        kind="review",
        title="结果复核",
        short_label="结果复核",
        category="output",
        sort_order=100,
    ),
    "completed": ExecutionStage(
        kind="completed",
        title="任务已完成",
        short_label="已完成",
        category="output",
        sort_order=105,
    ),
    "failed": ExecutionStage(
        kind="failed",
        title="任务执行失败",
        short_label="执行失败",
        category="output",
        sort_order=110,
    ),
    "queued": ExecutionStage(
        kind="queued",
        title="任务已创建",
        short_label="已创建",
        category="runtime",
        sort_order=2,
    ),
    "cancelled": ExecutionStage(
        kind="cancelled",
        title="任务已取消",
        short_label="已取消",
        category="output",
        sort_order=115,
    ),
    "resume": ExecutionStage(
        kind="resume",
        title="任务恢复中",
        short_label="恢复执行",
        category="runtime",
        sort_order=12,
    ),
    "progress": ExecutionStage(
        kind="progress",
        title="系统进度",
        short_label="系统进度",
        category="runtime",
        sort_order=999,
        supports_artifacts=False,
    ),
}


def get_stage(kind: str) -> ExecutionStage | None:
    """Return the ExecutionStage for a given kind, or None if unknown."""
    return EXECUTION_STAGES.get(kind)


def stage_title(kind: str, default: str | None = None) -> str:
    """Return the title for a stage kind, or a default when missing."""
    stage = get_stage(kind)
    return stage.title if stage else (default or kind)


def stage_short_label(kind: str, default: str | None = None) -> str:
    """Return the short UI label for a stage kind, or a default when missing."""
    stage = get_stage(kind)
    return stage.short_label if stage else (default or kind)


def stage_category(kind: str, default: str = "runtime") -> str:
    """Return the stage category used by execution timeline consumers."""
    stage = get_stage(kind)
    return stage.category if stage else default


def stage_sort_order(kind: str, default: int = 999) -> int:
    """Return a stable sort order for execution nodes of the same timestamp."""
    stage = get_stage(kind)
    return stage.sort_order if stage else default

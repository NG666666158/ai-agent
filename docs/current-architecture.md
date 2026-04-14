# Orion Agent 当前架构说明

## 1. 系统目标

Orion Agent 当前是一套面向单任务执行的 AI Agent MVP，核心能力包括：

- 任务解析：把用户输入转成结构化目标、约束和输出要求。
- 规划执行：生成步骤列表，并按步骤推进执行。
- 工具调用：支持本地文件读取、联网检索、文本摘要和 Markdown 封装。
- 记忆管理：支持短期任务记忆和长期向量记忆召回。
- 流式交付：前端通过 SSE 获取系统进度和回答正文的增量更新。
- 结果复核：在交付完成后执行评审，必要时触发重规划并重新生成答案。

## 2. 当前唯一主实现

后端主实现已经收敛到以下目录：

- `src/orion_agent/core/runtime_agent.py`
- `src/orion_agent/core/execution_engine.py`
- `src/orion_agent/core/state_machine.py`
- `src/orion_agent/core/tools.py`
- `src/orion_agent/core/memory.py`
- `src/orion_agent/core/repository.py`

前端主实现位于：

- `frontend/src/NewApp.tsx`
- `frontend/src/components/`
- `frontend/src/pages/`

历史遗留的双轨实现已不再作为主链路使用，后续开发应继续围绕上述文件演进。

## 3. 执行主链路

任务执行主流程如下：

1. API 接收 `TaskCreateRequest`
2. `AgentService` 创建任务记录并初始化进度
3. 解析器生成 `ParsedGoal`
4. 长期记忆召回相关经验
5. 规划器产出步骤清单
6. `ExecutionEngine` 逐步执行计划与工具调用
7. 交付步骤流式输出正文草稿
8. 反思器评审结果质量
9. 若评审失败且未超过上限，则进入重规划并重新生成
10. 任务完成后写入长期记忆

状态流转由 `state_machine.py` 统一约束：

- `CREATED -> PARSED -> PLANNED -> RUNNING -> REFLECTING -> COMPLETED/FAILED`
- 工具调用过程中允许 `RUNNING <-> WAITING_TOOL`
- 新增 `REPLANNING` 状态，用于承接联网失败降级和评审失败修订

## 4. 迭代 1 已落地能力

### 4.1 失败分类

当前引入了统一失败分类 `FailureCategory`：

- `INPUT_ERROR`
- `NETWORK_ERROR`
- `TOOL_TIMEOUT`
- `TOOL_UNAVAILABLE`
- `PERMISSION_DENIED`
- `VALIDATION_ERROR`
- `REVIEW_FAILED`
- `INTERNAL_ERROR`

任务级和工具调用级都保留失败分类与失败消息，便于前端展示和后续统计。

### 4.2 工具重试机制

工具定义支持 `max_retries`，全局配置支持：

- `AGENT_TOOL_MAX_RETRIES`
- `AGENT_REPLAN_LIMIT`

其中：

- `web_search` 为可重试工具
- `read_local_file`、`generate_markdown` 默认为不可重试
- 每次尝试都会写入 `ToolInvocation`
- `retry_count` 会累积到任务记录

### 4.3 重规划状态流

当前有两类重规划触发场景：

- 联网检索失败：自动降级为离线执行，并进入一次 `REPLANNING`
- 结果评审失败：如果未超过上限，则根据评审总结和清单重新生成最终答案

### 4.4 流式进度与正文

当前前端可以分别接收：

- 系统进度：解析输入、整理约束、检索记忆、生成计划、执行步骤、复核等
- 回答生成：正文草稿按 chunk 流式刷新

## 5. 关键数据模型

### TaskRecord

核心字段：

- `status`
- `parsed_goal`
- `steps`
- `result`
- `live_result`
- `retry_count`
- `replan_count`
- `failure_category`
- `failure_message`
- `tool_invocations`
- `progress_updates`
- `review`

### ToolInvocation

关键字段：

- `tool_name`
- `status`
- `input_payload`
- `output_preview`
- `error`
- `failure_category`
- `attempt_count`

## 6. 当前边界与后续演进

当前仍属于 MVP 阶段，下面这些能力是下一阶段重点：

- 权限确认流：高风险工具调用前的显式确认
- 任务详情页：查看完整步骤、工具输入输出、失败原因和导出结果
- 会话层：chat session、history、多轮上下文追溯
- 记忆管理页：浏览、过滤、删除、回放历史记忆

## 7. 建议的后续开发顺序

建议严格按以下顺序推进：

1. 迭代 1：继续补齐执行内核的稳定性和观测字段
2. 迭代 2：补权限确认、任务详情、工具调用详情与导出能力
3. 迭代 3：补会话层、历史追溯和记忆管理页

这样可以先稳住执行内核，再补可视化与交互层，最后接入长期使用场景。

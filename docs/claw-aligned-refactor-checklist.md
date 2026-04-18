# 对齐 Claw Code 的重构实施清单 v1

> 状态说明：本文档记录的是一轮对齐 claw code 思路的重构实施清单。其主体内容已基本落地，当前应主要作为历史重构记录与专题参考文档使用；统一基线请优先参考 [enterprise-stability-roadmap-v1.md](C:/github/ai-agent/ai-agent/docs/enterprise-stability-roadmap-v1.md) 和 [next-development-checklist.md](C:/github/ai-agent/ai-agent/docs/next-development-checklist.md)。

本文档是在当前 `Orion Agent` 已具备 Web 控制台、会话、记忆、画像和可视化执行链路的基础上，进一步向 `claw code` 的“运行时平台化”思路靠拢的实施清单。

目标不是把项目改造成 `claw code` 的克隆版本，而是保留当前项目的产品优势，同时补齐运行时内核、执行注册、权限治理和上下文治理能力。

## 一、重构目标

本轮重构聚焦 4 个目标：

1. 把当前 `AgentService` 中过于集中的职责继续拆分，形成更稳定的运行时内核边界。
2. 把“步骤执行”升级为“带元数据的执行节点系统”，让恢复、重规划和前端展示共用同一套模型。
3. 把工具、检索、记忆、画像等能力从业务逻辑中剥离成更清晰的能力层。
4. 为后续权限系统、插件化能力和多运行模式打基础。

## 二、重构原则

1. 不推翻当前可运行主链路，采用渐进式重构。
2. 先拆边界，再换实现，保证 API 和前端主流程尽量兼容。
3. 前端优先继续消费统一结构，不再新增新的临时字段分支。
4. 每个故事都必须可独立验证，适合交给 Ralph 单轮完成。

## 三、目标架构

### 1. Runtime 层

职责：

- 统一任务生命周期
- 统一运行入口与恢复入口
- 统一事件流和状态切换

建议模块：

- `src/orion_agent/core/runtime/agent_runtime.py`
- `src/orion_agent/core/runtime/contracts.py`
- `src/orion_agent/core/runtime/runtime_events.py`

### 2. Execution 层

职责：

- 定义执行节点注册表
- 执行节点调度
- 失败恢复与重规划

建议模块：

- `src/orion_agent/core/execution/execution_registry.py`
- `src/orion_agent/core/execution/executor.py`
- `src/orion_agent/core/execution/recovery_policy.py`

### 3. Context 层

职责：

- 构建上下文分层
- 控制上下文预算
- 产出上下文构建说明与来源追溯

建议模块：

- `src/orion_agent/core/context/context_builder.py`
- `src/orion_agent/core/context/context_budget.py`
- `src/orion_agent/core/context/citation_map.py`

### 4. Capability 层

职责：

- 提供 LLM、工具、检索、记忆、画像能力
- 为权限和元数据暴露统一接口

建议模块：

- `src/orion_agent/core/capabilities/tools/`
- `src/orion_agent/core/capabilities/retrieval/`
- `src/orion_agent/core/capabilities/memory/`
- `src/orion_agent/core/capabilities/profile/`

### 5. Governance 层

职责：

- 会话存储
- 历史追溯
- 记忆治理
- 画像治理

建议模块：

- `src/orion_agent/core/session/session_store.py`
- `src/orion_agent/core/memory/memory_store.py`
- `src/orion_agent/core/profile/profile_store.py`

### 6. Product 层

职责：

- 前端只消费稳定 runtime schema
- 不再让页面自己拼凑执行语义

重点页面：

- `frontend/src/pages/ConsolePage.tsx`
- `frontend/src/pages/TasksPage.tsx`
- `frontend/src/pages/SessionsPage.tsx`

## 四、P0 / P1 / P2 清单

### P0

#### P0-1：统一唯一执行节点实现

预计交付物：

- 删除 `build_execution_nodes` / `build_execution_nodes_v2` 双轨并存
- 保留一套唯一执行节点构建逻辑
- 单元测试补齐

#### P0-2：拆出 ContextBuilder

预计交付物：

- 从 `runtime_agent.py` 中拆出上下文构建器
- 明确各 context layer 的来源、预算和构建说明
- 前端继续使用原字段，但由新 builder 负责产出

#### P0-3：引入 ExecutionRegistry

预计交付物：

- 为关键执行节点建立注册表
- 节点具备 kind、title、status、artifacts、retry policy 等元数据
- 前后端围绕统一节点元数据工作

#### P0-4：拆出 RecoveryPolicy

预计交付物：

- 将失败分类与恢复决策从 `AgentService` 中抽离
- 保留现有重试、跳过、重建后半段计划、从检查点重规划能力
- 为后续策略扩展打基础

### P1

#### P1-1：ToolRegistry 升级为 ToolPool

预计交付物：

- 工具具备类别、权限级别、超时、重试、展示标签等元数据
- 高风险工具确认更统一

#### P1-2：后端 citation map 标准化

预计交付物：

- 后端直接产出段落与来源映射
- 减少前端自行猜测引用关系

#### P1-3：SessionStore 标准化

预计交付物：

- 会话摘要、分支续聊、画像快照逻辑收口
- 会话追溯链路更稳定

### P2

#### P2-1：插件化能力预留

预计交付物：

- 检索策略扩展点
- 工具元数据扩展点
- 引用格式化扩展点

#### P2-2：多运行模式预留

预计交付物：

- Web / API / CLI / batch 模式边界说明
- 统一 runtime contract

## 五、推荐的 Ralph 拆分故事

为了适合自动化执行，本轮建议先拆成下面 5 个故事：

1. `US-R1`：统一唯一执行节点实现
2. `US-R2`：拆出 ContextBuilder 并接回主链路
3. `US-R3`：引入 ExecutionRegistry 并迁移关键节点
4. `US-R4`：拆出 RecoveryPolicy 与失败恢复决策
5. `US-R5`：为 ToolPool 和 citation map 预留标准接口

## 六、建议的执行顺序

1. 先做 `US-R1`，消除双轨节点实现。
2. 再做 `US-R2`，把上下文治理从主编排器里拆出来。
3. 然后做 `US-R3`，把执行节点元数据正规化。
4. 再做 `US-R4`，让恢复与重规划真正模块化。
5. 最后做 `US-R5`，为下一轮平台化能力做接口预留。

## 七、验收标准

本轮重构完成后，至少应满足：

1. `runtime_agent.py` 的职责比当前更聚焦，不再承担过多上下文构建和恢复细节。
2. 执行节点在后端只有一个主实现来源。
3. 上下文分层可以被独立测试，而不依赖完整任务执行。
4. 恢复策略可以被独立测试，而不依赖完整前端流程。
5. 前端现有控制台和任务详情页无需推倒重来即可继续工作。

## 八、风险提示

1. 当前项目仍在快速演进，重构过程中不要同步推进大规模 UI 改版。
2. `Ralph` 更适合做小步、可验证的 story，不适合一轮吞掉整套架构升级。
3. 任何涉及 `runtime_agent.py` 的改动都必须配套后端回归测试。

## 九、扩展点说明（US-R5）

本节描述运行时各能力层的扩展点，为后续插件化和权限工作提供接口约定。

### 9.1 工具元数据扩展（ToolDefinition）

`src/orion_agent/core/models.py` 中的 `ToolDefinition` 为工具能力提供了完整元数据接口：

```python
class ToolDefinition(BaseModel):
    name: str                          # 工具唯一标识符
    description: str                   # 工具功能描述
    input_schema: dict[str, str]       # 输入参数 schema
    output_schema: dict[str, str]      # 输出结果 schema
    timeout_ms: int = 15_000          # 超时毫秒数
    permission_level: ToolPermission    # SAFE / CONFIRM / RESTRICTED
    max_retries: int = 0              # 最大重试次数
    # --- 扩展字段 ---
    category: str | None = None        # 工具类别，如 "search"、"file"、"generation"
    display_name: str | None = None    # 前端展示用全称
    display_label: str | None = None   # 前端展示用短标签（徽章/标签）
```

扩展方式：
- 在 `ToolRegistry._definitions` 中注册新工具时，填写 `category`、`display_name`、`display_label` 字段
- `category` 可选值（可自行扩展）：`"search"`、`"file"`、`"text"`、`"generation"`、`"analysis"`
- `permission_level` 可选值：`ToolPermission.SAFE`（无需确认）、`CONFIRM`（需用户确认）、`RESTRICTED`（高风险）

### 9.2 引用映射扩展（CitationMap）

`src/orion_agent/core/citation_map.py` 提供了后端引用映射的标准化扩展表面：

```python
CITATION_KINDS = {
    "memory":          "长期记忆召回",
    "profile":         "用户画像事实",
    "session_message": "会话消息",
    "source_summary":  "外部材料摘要",
    "web_search":      "网络搜索结果",
    "file":            "本地文件内容",
}
```

`CitationMap` 类是引用注册的主扩展入口：

```python
citation_map.add_source(
    kind="web_search",
    label="搜索结果 #1",
    detail="...",
    source_record_id="...",
    source_task_id="...",
) -> source_id  # 返回注册的来源 ID

citation_map.add_paragraph(
    paragraph_index=0,
    paragraph_text="...",
    source_ids=["cite_xxx", "cite_yyy"],
    source_labels=["搜索结果 #1", "会话消息 #2"],
)
```

扩展方式：
- 新增 `CITATION_KINDS` 条目以支持新的来源类型
- 通过 `CitationMap.add_source()` 注册来源，通过 `add_paragraph()` 建立段落-来源映射
- `source_task_id` 字段支持跨任务引用追溯

# Orion Agent 当前架构说明

## 1. 文档定位

本文档用于描述当前仓库已经落地的主架构、核心边界、主要数据流，以及与“真实完成度基线”的对应关系。

它不再是早期的理想化设计稿，而是面向当前代码现实的架构说明。

统一参照关系如下：

- “项目现在到底做到了什么”请先看 [current-progress-baseline.md](C:/github/ai-agent/ai-agent/docs/current-progress-baseline.md)
- “项目当前是怎么组织和运行的”请看本文档

---

## 2. 项目定位

Orion Agent 当前是一个中文 Agent 原型平台，目标不是只完成一次性任务演示，而是持续建设以下能力：

- 从自然语言输入到任务执行结果的完整链路
- 会话级历史管理与上下文续聊
- 长期记忆与用户画像的跨会话复用
- 工具调用、检索、引用、恢复过程的可视化展示
- 逐步向更稳定、更可恢复、更可治理的执行内核演进

当前阶段判断：

- 已经超过 MVP
- 还不是企业级生产平台
- 正处于“原型平台已成形，平台化改造持续推进”的阶段

---

## 3. 当前唯一主实现

当前后端唯一主执行入口是：

- [runtime_agent.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/runtime_agent.py)

这意味着：

- 后续功能增强应继续围绕 `runtime_agent.py` 收口
- 不应再额外维护第二套并行主流程
- 所有恢复、重规划、上下文分层、记忆注入、事件流输出，都应回到这条主实现上统一治理

当前主链路可以概括为：

1. API 接收前端请求
2. `AgentService` 创建任务、会话和消息记录
3. 组装当前轮上下文、短期历史、长期记忆、用户画像
4. 解析任务目标与约束
5. 生成执行计划
6. 执行引擎推进步骤并调用工具
7. 在执行中持续产出系统进度事件和流式正文
8. 必要时进入失败恢复、重试或重规划
9. 写回任务结果、会话消息、记忆、画像和引用信息

---

## 4. 分层结构

### 4.1 API 层

位置：

- [tasks.py](C:/github/ai-agent/ai-agent/src/orion_agent/api/routes/tasks.py)
- [sessions.py](C:/github/ai-agent/ai-agent/src/orion_agent/api/routes/sessions.py)
- [memories.py](C:/github/ai-agent/ai-agent/src/orion_agent/api/routes/memories.py)
- [system.py](C:/github/ai-agent/ai-agent/src/orion_agent/api/routes/system.py)

职责：

- 接收前端请求
- 校验输入数据
- 暴露任务、会话、记忆、画像和系统状态接口
- 提供任务流式输出接口

当前状态：

- 主接口集已成形
- 后续仍需继续补强权限校验、错误分类与审计能力

### 4.2 编排层

位置：

- [runtime_agent.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/runtime_agent.py)

职责：

- 组织 Agent 主执行流
- 串联 Parser、Planner、ExecutionEngine、Reflection、Memory、Profile 等能力
- 管理任务状态、会话写入、恢复策略和结果回写

当前状态：

- 这是当前系统最关键的主控层
- 已逐步从早期大而杂的流程编排，向更明确的 runtime 边界收敛
- 后续还需要继续“收口”，避免新的业务逻辑回流到分散入口

### 4.3 执行内核层

位置：

- [execution_engine.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/execution_engine.py)
- [state_machine.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/state_machine.py)
- [planner.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/planner.py)
- [reflection.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/reflection.py)

职责：

- 把规划步骤推进为真实执行过程
- 记录执行节点、工具调用、失败信息、恢复信息与结果事件
- 在校验失败或执行失败时触发修复、重试、恢复或重规划

当前状态：

- 已有执行注册表、恢复策略、节点抽象、失败分类等基础骨架
- 当前轮 claw code 对齐重构已经把不少运行时能力从“散逻辑”推进到“可治理结构”
- 但“只重建后半段计划”“跳过失败步骤继续执行”等高级恢复策略仍属于部分完成

### 4.4 能力支撑层

位置：

- [tools.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/tools.py)
- [llm_runtime.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/llm_runtime.py)
- [prompts.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/prompts.py)
- [memory.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/memory.py)
- [profile.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/profile.py)
- [repository.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/repository.py)
- [vector_store.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/vector_store.py)
- [embedding_runtime.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/embedding_runtime.py)

职责：

- 提供 LLM 调用与 fallback
- 提供工具注册与工具执行
- 提供记忆、画像、持久化、向量检索等底层能力
- 支撑引用、来源提示、召回原因与画像注入

当前状态：

- 这部分已经具备可运行的主能力
- RAG 已有“混合召回 + 最小 rerank + 命中原因返回”的最小增强版
- 但检索评估、参数治理、长期数据治理和更稳定的上下文预算策略仍需继续做实

### 4.5 前端体验层

位置：

- [NewApp.tsx](C:/github/ai-agent/ai-agent/frontend/src/NewApp.tsx)
- [AppShell.tsx](C:/github/ai-agent/ai-agent/frontend/src/components/AppShell.tsx)
- [ConsolePage.tsx](C:/github/ai-agent/ai-agent/frontend/src/pages/ConsolePage.tsx)
- [TasksPage.tsx](C:/github/ai-agent/ai-agent/frontend/src/pages/TasksPage.tsx)
- [SessionsPage.tsx](C:/github/ai-agent/ai-agent/frontend/src/pages/SessionsPage.tsx)
- [MemoriesPage.tsx](C:/github/ai-agent/ai-agent/frontend/src/pages/MemoriesPage.tsx)
- [ProfilePage.tsx](C:/github/ai-agent/ai-agent/frontend/src/pages/ProfilePage.tsx)
- [SettingsPage.tsx](C:/github/ai-agent/ai-agent/frontend/src/pages/SettingsPage.tsx)

职责：

- 展示会话列表、当前会话、回答区与系统进度
- 以可折叠方式展示思考过程、检索链路、工具调用和恢复信息
- 渲染 Markdown 回答与引用脚注
- 提供会话、记忆、画像、任务详情等管理入口

当前状态：

- 已形成 Agent 控制台雏形
- 主体交互已经成形
- 后续还需要继续完成中文文案统一、复杂 Markdown 场景精修和异常态体验统一

---

## 5. 当前关键数据模型

### 5.1 TaskRecord

关键字段：

- `status`
- `parsed_goal`
- `steps`
- `result`
- `live_result`
- `retry_count`
- `replan_count`
- `failure_category`
- `failure_message`
- `recalled_memories`
- `profile_hits`
- `tool_invocations`
- `progress_updates`
- `pending_approvals`
- `context_layers`
- `checkpoint`
- `replan_history`

作用：

- 承载任务执行结果与过程态信息
- 是任务追溯、恢复展示、系统进度展示的主要基础模型

### 5.2 ChatSession

关键字段：

- `title`
- `message_count`
- `context_summary`
- `summary_updated_at`
- `source_session_id`
- `profile_snapshot`

作用：

- 承载会话级信息
- 支撑历史查看、分支续聊、上下文摘要和跨轮会话体验

### 5.3 LongTermMemoryRecord

关键字段：

- `scope`
- `topic`
- `summary`
- `details`
- `tags`
- `embedding`
- `source`
- `versions`
- `memory_type`
- `score`
- `hit_reason`

作用：

- 承载长期记忆与召回元数据
- 支撑混合召回、命中解释与引用映射

### 5.4 UserProfileFact

关键字段：

- `category`
- `label`
- `value`
- `confidence`
- `status`
- `superseded_by`
- `source_session_id`
- `source_task_id`

作用：

- 承载用户偏好与用户画像事实
- 支撑跨会话注入、画像编辑、冲突合并和回答个性化

---

## 6. 当前已落地的核心能力

### 6.1 已完成

- 基础任务解析、规划、执行、结果生成主链路
- 流式回答与系统进度展示
- 会话历史与上下文摘要
- 长期记忆与用户画像基础闭环
- 记忆来源提示与引用脚注
- RAG 最小增强版
- 基础测试体系
- 当前轮 claw code 对齐重构主线

### 6.2 部分完成

- 可恢复执行流
- 重规划机制
- 上下文分层与预算控制
- 记忆治理闭环
- 前端中文体验统一
- 文档统一

### 6.3 未开始或明显不足

- 多用户隔离与用户体系
- 权限矩阵与审计体系
- 企业级部署与运维治理
- 企业级稳定性指标、压测与故障注入
- 插件化扩展生态

---

## 7. 当前架构的主要优点

### 7.1 已从“单次任务脚本”演进为“可持续扩展的 Agent 工作台”

当前系统已经不再只关心最终答案，而是能够展示：

- 任务如何被解析
- 记忆如何被召回
- 工具如何被调用
- 结果如何被修复
- 来源如何映射到正文

### 7.2 已有平台化重构基础

当前架构已经具备继续向企业级能力推进的几个重要起点：

- 唯一主实现入口
- 执行注册表与恢复策略
- 会话、记忆、画像的模型边界
- 前后端事件与追溯信息的基本通路

### 7.3 已具备继续强化 RAG 和会话治理的土壤

当前记忆系统虽然仍偏最小实现，但已经有：

- 召回分数
- 命中原因
- 记忆类型
- 段落引用映射

这为后续做更强检索、召回解释与上下文治理提供了明确基础。

---

## 8. 当前不足与风险

### 8.1 恢复流尚未完全平台化

虽然已经有失败分类、重试和恢复策略，但仍存在：

- 恢复判定边界不够稳定
- 局部恢复与重规划切换规则不够明确
- 恢复状态与前端表达的一致性仍需继续打磨

### 8.2 上下文分层仍缺少统一预算治理

当前已经开始分层，但还没有真正完成：

- 统一 token 预算
- 裁剪优先级规则
- 多轮续聊压缩策略稳定化

### 8.3 平台级用户边界还没有建立

当前的会话、记忆、画像更偏单用户研发态，尚未进入：

- 用户身份体系
- 多用户隔离
- 组织级数据边界

### 8.4 生产能力尚未落地

当前仍缺：

- 系统监控
- 审计
- 灰度回滚
- 备份恢复
- 稳定性指标体系

---

## 9. 下一步架构优先级

### P0

- 收口 README、架构文档、路线图与任务清单
- 完成执行内核恢复流的统一收口
- 做实上下文分层与压缩策略

### P1

- 增强记忆治理、画像治理与 RAG 质量
- 收尾前端控制台体验统一
- 强化引用追溯和命中解释

### P2

- 建立多用户体系
- 建立权限矩阵与审计能力
- 补齐生产部署与运维治理

---

## 10. 统一结论

当前 Orion Agent 的架构状态可以概括为：

> 后端已经初步形成以 `runtime_agent.py` 为主入口、以执行内核为中心、以会话/记忆/画像为支撑、以前端控制台为展示面的 Agent 原型平台结构；当前最重要的工作不是继续堆更多页面，而是把恢复流、上下文治理、记忆治理和平台边界继续收口做实。

这就是当前代码层面最值得统一的架构认知。

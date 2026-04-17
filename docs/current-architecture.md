# Orion Agent 当前架构说明

## 1. 项目定位

Orion Agent 当前是一个面向“任务执行、多轮会话、长期记忆、来源追溯”的 AI Agent 原型系统。

它已经从早期的单轮任务闭环演化为一个带控制台、会话页、记忆页、画像页和任务追溯能力的工作台形态。当前更适合继续增强执行内核和治理能力，而不是再平铺更多新页面。

## 2. 当前唯一主实现

当前后端的唯一主编排入口是：

- [runtime_agent.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/runtime_agent.py)

围绕它形成的主链路是：

1. API 接收请求
2. `AgentService` 创建任务记录和会话消息
3. 构建上下文分层
4. 解析任务
5. 召回长期记忆与用户画像
6. 规划执行步骤
7. 执行引擎推进步骤和工具调用
8. 流式输出正文
9. 结果评审与必要重规划
10. 写入长期记忆、画像和会话消息

当前没有第二套并行编排主实现，后续开发应继续围绕这条主链路增强。

## 3. 分层结构

### 3.1 API 层

位置：

- [tasks.py](/C:/github/ai-agent/ai-agent/src/orion_agent/api/routes/tasks.py)
- [sessions.py](/C:/github/ai-agent/ai-agent/src/orion_agent/api/routes/sessions.py)
- [memories.py](/C:/github/ai-agent/ai-agent/src/orion_agent/api/routes/memories.py)
- [system.py](/C:/github/ai-agent/ai-agent/src/orion_agent/api/routes/system.py)

职责：

- 接收前端请求
- 验证输入模型
- 暴露任务、会话、记忆、画像和系统状态接口
- 提供任务 SSE 流式输出

### 3.2 编排层

位置：

- [runtime_agent.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/runtime_agent.py)

职责：

- 创建任务记录、会话记录和消息记录
- 调用解析器、规划器、执行引擎、评审器和记忆管理器
- 管理恢复、取消、审批、重规划
- 维护任务状态、进度和 checkpoint

### 3.3 执行内核

位置：

- [execution_engine.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/execution_engine.py)
- [state_machine.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/state_machine.py)
- [planner.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/planner.py)
- [reflection.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/reflection.py)

职责：

- 将规划步骤推进为真实执行过程
- 在执行中记录工具调用、失败、进度和结果
- 在评审失败时执行结果修订
- 保证任务状态流转合法

### 3.4 能力支撑层

位置：

- [tools.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/tools.py)
- [llm_runtime.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/llm_runtime.py)
- [prompts.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/prompts.py)
- [memory.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/memory.py)
- [profile.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/profile.py)
- [repository.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/repository.py)
- [vector_store.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/vector_store.py)
- [embedding_runtime.py](/C:/github/ai-agent/ai-agent/src/orion_agent/core/embedding_runtime.py)

职责：

- 提供 LLM 调用与 fallback
- 提供工具注册与工具执行
- 提供短期记忆、长期记忆与用户画像能力
- 提供持久化与向量召回

### 3.5 前端体验层

位置：

- [NewApp.tsx](/C:/github/ai-agent/ai-agent/frontend/src/NewApp.tsx)
- [AppShell.tsx](/C:/github/ai-agent/ai-agent/frontend/src/components/AppShell.tsx)
- [ConsolePage.tsx](/C:/github/ai-agent/ai-agent/frontend/src/pages/ConsolePage.tsx)
- [TasksPage.tsx](/C:/github/ai-agent/ai-agent/frontend/src/pages/TasksPage.tsx)
- [SessionsPage.tsx](/C:/github/ai-agent/ai-agent/frontend/src/pages/SessionsPage.tsx)
- [MemoriesPage.tsx](/C:/github/ai-agent/ai-agent/frontend/src/pages/MemoriesPage.tsx)
- [ProfilePage.tsx](/C:/github/ai-agent/ai-agent/frontend/src/pages/ProfilePage.tsx)
- [SettingsPage.tsx](/C:/github/ai-agent/ai-agent/frontend/src/pages/SettingsPage.tsx)

职责：

- 发起任务和管理会话
- 展示系统进度与流式回答
- 展示任务追溯、长期记忆和用户画像
- 展示来源命中与段落级引用脚注

## 4. 当前核心数据模型

### TaskRecord

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

### ChatSession

关键字段：

- `title`
- `message_count`
- `context_summary`
- `summary_updated_at`
- `source_session_id`
- `profile_snapshot`

### LongTermMemoryRecord

关键字段：

- `scope`
- `topic`
- `summary`
- `details`
- `tags`
- `embedding`
- `source`
- `versions`

### UserProfileFact

关键字段：

- `category`
- `label`
- `value`
- `confidence`
- `status`
- `superseded_by`
- `source_session_id`
- `source_task_id`

## 5. 当前已落地能力

### 5.1 执行链路

- 任务解析
- 步骤规划
- 顺序执行
- 流式正文输出
- 结果评审
- 一次重规划修订

### 5.2 失败治理

- 失败分类
- 工具重试
- 搜索与向量召回回退
- 评审失败后的修订路径

### 5.3 权限确认

- 对高风险本地文件读取进行确认
- 挂起任务并等待审批
- 审批后恢复执行

### 5.4 会话与上下文

- 会话持久化
- 多轮消息记录
- 会话压缩摘要
- 分叉续聊
- 会话侧任务追溯

### 5.5 记忆与画像

- 长期记忆召回与编辑
- 语义召回与本地回退
- 画像抽取、编辑、冲突合并
- 跨会话画像注入
- 来源提示与段落级引用脚注

## 6. 当前边界与不足

虽然项目结构已经完整，但仍处在“原型到产品化”的过渡阶段，主要不足如下：

- 任务 checkpoint 仍偏轻量，缺少更细的阶段快照
- 重规划原因仍不够细，缺少结构化恢复策略
- 上下文分层已有雏形，但还没有严格预算和裁剪策略
- 结构化 citation map 还没有在后端产出，目前回答引用仍是前端映射
- 没有多用户隔离、用户身份和组织边界
- 权限确认仍是点状能力，不是完整风险矩阵
- 部署和监控具备基础能力，但不具备生产级治理能力

## 7. 下一阶段架构重点

下一阶段应优先推进三件事：

1. 执行内核增强
   - 更细 checkpoint
   - 恢复能力增强
   - 重规划状态流增强
   - 上下文分层治理

2. 来源与记忆治理增强
   - 后端结构化 citation map
   - 记忆命中可解释
   - 画像与记忆的审阅和可控能力

3. 用户体系与生产化
   - 多用户隔离
   - 角色权限
   - 审计日志
   - 生产部署与备份恢复

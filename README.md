# Orion Agent

Orion Agent 是一个面向“任务执行、多轮会话、长期记忆、用户画像、可视化执行链路”的中文 AI Agent 原型项目。

它已经不是最早那种只演示一次任务调用的 MVP，而是一个具备以下主体能力的 Agent 工作台：

- 能接收自然语言任务并完成解析、规划、执行、校验与必要重规划
- 能在前端展示流式回答、系统进度、工具调用与执行轨迹
- 能管理会话、历史消息、上下文压缩与任务追溯
- 能写入、召回、编辑长期记忆，并给出命中来源提示
- 能抽取和注入用户画像，在新会话中自动利用跨会话偏好
- 能通过测试与运行时日志支持后续持续重构

当前项目定位不是“企业级生产平台”，而是：

> 一个已经完成主体形态、正在继续平台化和工程化的 Agent 原型系统

如果你要把它理解成一个阶段判断，可以这样看：

- 产品可演示完成度：较高
- 单机原型可用完成度：较高
- 平台化与工程化完成度：中等偏上
- 企业级生产能力完成度：仍需继续建设

统一基线请优先参考：

- [当前架构进展基线](C:/github/ai-agent/ai-agent/docs/current-progress-baseline.md)
- [当前架构说明](C:/github/ai-agent/ai-agent/docs/current-architecture.md)

## 当前真实完成度

截至 `2026-04-18`，当前项目更接近：

> “可运行的 Agent 原型平台 + 执行内核平台化改造中后段”

这意味着：

- 主体链路已经成形，不是从 0 到 1 的阶段
- 但也还没有达到真正企业级稳定平台的完成态

建议按以下认知推进后续开发：

- 已完成：基础产品形态、流式回答、会话层、记忆与画像主链路、RAG 最小增强版、引用追溯、基础测试体系、当前轮 claw code 对齐重构
- 部分完成：恢复流、重规划、上下文分层预算、记忆治理闭环、前端中文统一、文档统一
- 未开始或明显不足：多用户体系、权限矩阵、审计能力、生产部署、企业级稳定性治理、插件化生态

## 核心能力

### 1. Agent 执行链路

- 将自然语言任务解析为结构化目标、约束和输出要求
- 基于 Planner 生成可执行步骤
- 通过执行引擎推进步骤、调用工具、记录进度与失败
- 在执行中流式输出“系统进度”和“回答生成”
- 在必要时执行重试、恢复或重规划

### 2. 会话层

- 支持 `chat session`
- 支持历史消息持久化与会话列表展示
- 支持上下文摘要、压缩与跨轮续聊
- 支持从会话回看关联任务

### 3. 记忆与用户画像

- 支持长期记忆写入、检索、编辑与软删除
- 支持语义召回、混合召回与最小 rerank
- 支持偏好提取器与用户画像存储
- 支持新会话自动注入画像与偏好
- 支持来源提示、命中原因、段落级引用脚注

### 4. 前端控制台体验

- 左侧历史会话与当前会话切换
- 右侧当前对话区与当前会话记录
- 回答区支持 Markdown 渲染
- 思考过程与执行链路可折叠展示
- 支持系统进度与回答生成的分区显示

### 5. 测试与可追溯能力

- 已建立 `tests/` 模块化结构
- 已覆盖执行引擎、恢复策略、会话层、记忆与画像等关键模块
- 已提供一键运行测试并输出中文 Markdown 报告的脚本

## 项目结构

```text
src/orion_agent/
  api/routes/              # FastAPI 路由层
  core/                    # 解析、规划、执行、状态机、记忆、画像、工具、LLM 等核心逻辑
  frontend_routes.py       # 前端静态资源路由
  main.py                  # 后端入口

frontend/src/
  components/              # 通用组件与布局
  pages/                   # 控制台、任务、会话、记忆、画像、设置等页面
  api.ts                   # 前端接口封装

docs/
  current-progress-baseline.md   # 当前真实完成度基线
  current-architecture.md        # 当前架构说明
  next-development-checklist.md  # 后续任务清单（部分内容待同步）
  claw-aligned-refactor-checklist.md

tests/
  unit/                    # 单元测试
  integration/             # 集成测试
  fixtures/                # 场景数据
  scripts/                 # 测试运行与报告脚本

deploy/
  docker-compose.yml
  start-local.ps1
  start-stack.ps1
```

## 当前主实现说明

当前后端唯一主执行入口已经收敛到：

- [runtime_agent.py](C:/github/ai-agent/ai-agent/src/orion_agent/core/runtime_agent.py)

围绕它协作的核心模块包括：

- `planner.py`
- `execution_engine.py`
- `state_machine.py`
- `memory.py`
- `profile.py`
- `repository.py`
- `llm_runtime.py`

当前不应再维护第二套并行主流程；后续重构应继续围绕这条主实现收口。

## 本地启动

### 方式一：本地直启

```powershell
powershell -ExecutionPolicy Bypass -File deploy/start-local.ps1
```

默认地址：

- 前端与 API：`http://127.0.0.1:8011/`
- 健康检查：`http://127.0.0.1:8011/healthz`

### 方式二：Docker 启动

```powershell
powershell -ExecutionPolicy Bypass -File deploy/start-stack.ps1
```

默认会启动：

- `orion-agent`
- `orion-qdrant`
- `orion-prometheus`
- `orion-grafana`

## 关键配置

主要配置位于 `deploy/.env`：

- `LLM_PROVIDER=openai|minimax|fallback`
- `OPENAI_API_KEY`
- `MINIMAX_API_KEY`
- `MINIMAX_BASE_URL`
- `VECTOR_BACKEND=qdrant|local`
- `VECTOR_SERVICE_URL`
- `ALLOW_ONLINE_SEARCH=true|false`
- `AGENT_FORCE_FALLBACK=true|false`
- `AGENT_TOOL_MAX_RETRIES`
- `AGENT_REPLAN_LIMIT`

## 测试

运行全部测试并输出中文 Markdown 报告：

```powershell
python tests\scripts\run_all_tests_and_report.py
```

默认输出：

- `tests/TEST_REPORT.md`

## 下一步优先级

后续开发统一按以下顺序推进：

1. 文档统一收口  
   把 README、架构文档、路线图、开发清单全部和最新代码状态对齐。

2. 执行内核恢复流收尾  
   做实 checkpoint、失败分类、恢复策略、跳过失败步骤、仅重建后半段计划。

3. 上下文分层与压缩策略  
   明确短期上下文、长期记忆、用户画像、工具结果的分层装配与预算控制。

4. 记忆与画像治理增强  
   完善编辑、冲突合并、失效、纠错、人工确认等能力。

5. 多用户、权限与生产化能力  
   这是进入企业级稳定平台前必须补齐的一段。

## 说明

如果你接下来要继续开发这个项目，建议先读三份文档：

1. [当前架构进展基线](C:/github/ai-agent/ai-agent/docs/current-progress-baseline.md)
2. [当前架构说明](C:/github/ai-agent/ai-agent/docs/current-architecture.md)
3. [后续开发清单](C:/github/ai-agent/ai-agent/docs/next-development-checklist.md)

它们共同构成当前项目后续开发的统一认知基础。

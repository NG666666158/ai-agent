# Orion Agent

Orion Agent 是一个面向“任务执行 + 多轮会话 + 长期记忆 + 可追溯工作台”的 AI Agent 原型项目。

当前版本已经不再只是单次任务演示，而是具备了以下能力：

- 任务解析、规划、执行、反思和重规划
- 流式系统进度与流式回答输出
- 会话管理、历史追溯、上下文压缩
- 长期记忆召回、编辑、软删除、来源追踪
- 用户画像提取、跨会话注入、画像编辑与冲突合并
- 高风险操作确认
- 基础测试体系与中文测试报告

项目定位不是“生产级平台”，而是“可持续迭代的 Agent 原型工作台”。它适合继续向执行内核增强、上下文治理、多用户隔离和生产化能力演进。

## 当前能力

### 1. Agent 执行链路

- 将自然语言任务解析为结构化目标、约束和输出格式
- 基于规划器生成可执行步骤
- 支持本地文件读取、文本总结、联网搜索、Markdown 封装等工具
- 执行中持续产出系统进度和正文流式结果
- 在结果评审失败时触发重规划和修订

### 2. 会话层

- 支持 `chat session`
- 用户消息和助手消息按会话持久化
- 支持会话分叉续聊
- 支持多轮上下文压缩与摘要刷新
- 支持从会话侧回看关联任务

### 3. 记忆层

- 支持长期记忆写入与召回
- 支持语义召回和回退检索
- 支持记忆编辑、版本历史、软删除
- 支持来源任务 / 会话追溯

### 4. 画像层

- 支持从用户输入中抽取偏好事实
- 支持跨会话注入用户画像
- 支持画像编辑、状态切换、冲突合并
- 支持在回答区和系统进度区展示画像命中来源

### 5. 可观测与测试

- 支持任务轨迹、工具调用记录、Prometheus 指标
- 支持后端单元测试、API 测试、集成测试脚本
- 支持一键生成 Markdown 测试报告

## 项目结构

```text
src/orion_agent/
  api/routes/              # FastAPI 路由层
  core/                    # 解析、规划、执行、状态机、记忆、画像、工具、LLM 等核心逻辑
  frontend_routes.py       # 内置前端静态资源路由
  main.py                  # 服务入口

frontend/src/
  components/              # 页面壳与共享组件
  pages/                   # 控制台、任务、会话、记忆、画像、设置页
  api.ts                   # 前端 API 封装

deploy/
  docker-compose.yml       # 本地容器启动方式
  backend.Dockerfile       # 后端镜像构建
  start-local.ps1          # 本地直启脚本
  start-stack.ps1          # 容器栈启动脚本

docs/
  current-architecture.md  # 当前架构说明
  implementation-plan.md   # 当前阶段实施计划
  product-roadmap.md       # 产品路线图
  production.md            # 生产化部署说明

tests/
  unit/                    # 单元测试
  integration/             # 集成测试
  fixtures/                # 场景测试数据
  scripts/                 # 测试运行与报告脚本
```

## 页面说明

- `/`
  主控制台。发起任务、查看系统进度、流式回答、来源提示、会话消息。
- `/tasks`
  任务中心。查看任务详情、工具调用、导出结果、历史追溯。
- `/sessions`
  会话历史。查看会话消息、上下文摘要、分叉续聊、关联任务。
- `/memories`
  记忆管理。搜索、编辑、删除长期记忆，追溯版本和来源。
- `/profile`
  用户画像。查看跨会话偏好、编辑画像、处理冲突合并。
- `/settings`
  系统运行配置与健康状态。

## API 概览

### 任务

- `POST /api/tasks`
  同步创建并执行任务
- `POST /api/tasks/launch`
  异步启动任务
- `GET /api/tasks`
  获取任务列表
- `GET /api/tasks/{task_id}`
  获取任务详情
- `GET /api/tasks/{task_id}/stream`
  通过 SSE 获取任务流式更新
- `GET /api/tasks/{task_id}/trace`
  获取任务追溯信息
- `POST /api/tasks/{task_id}/confirm`
  处理高风险操作确认
- `POST /api/tasks/{task_id}/cancel`
  取消任务
- `POST /api/tasks/{task_id}/resume`
  恢复任务

### 会话

- `POST /api/sessions`
  创建会话
- `GET /api/sessions`
  获取会话列表
- `GET /api/sessions/{session_id}`
  获取会话详情
- `POST /api/sessions/{session_id}/refresh-summary`
  刷新会话摘要

### 记忆

- `GET /api/memories`
  获取长期记忆列表
- `GET /api/memories/search`
  搜索长期记忆
- `PUT /api/memories/{memory_id}`
  编辑长期记忆
- `DELETE /api/memories/{memory_id}`
  软删除长期记忆

### 画像

- `GET /api/system/profile`
  获取用户画像事实
- `PUT /api/system/profile/{fact_id}`
  编辑画像事实
- `POST /api/system/profile/{fact_id}/merge`
  合并画像事实

### 系统

- `GET /api/system/health`
  获取运行健康状态
- `GET /api/system/runtime`
  获取运行时配置摘要
- `GET /api/system/metrics`
  获取 Prometheus 指标

## 本地启动

### 方式一：本地直接启动

```powershell
powershell -ExecutionPolicy Bypass -File deploy/start-local.ps1
```

默认地址：

- 前端与 API: `http://127.0.0.1:8011/`
- 健康检查: `http://127.0.0.1:8011/healthz`

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

运行测试并生成 Markdown 报告：

```powershell
python tests\scripts\run_all_tests_and_report.py
```

输出文件：

- `tests/TEST_REPORT.md`

## 当前阶段判断

当前项目已经完成了从“单任务 Agent MVP”到“具备会话层和记忆层的可迭代原型工作台”的升级，但仍然不是生产级系统。

下一阶段建议按顺序推进：

1. 统一文档与项目认知，修正文档和代码的偏差
2. 增强执行内核：checkpoint、恢复、重规划、上下文分层
3. 强化会话和记忆治理：结构化引用、追溯、可控性
4. 补用户体系、权限体系与生产化部署能力

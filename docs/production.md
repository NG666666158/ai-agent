# Orion Agent 部署与生产化说明

## 1. 文档定位

本文档说明当前项目的部署形态、运行组件、环境变量、监控入口，以及目前距离真正生产级部署还差哪些能力。

需要特别说明：

- 当前项目已经具备本地运行和容器运行能力
- 但还不应被视为“已经完成企业级生产部署”

---

## 2. 当前已支持的运行形态

### 2.1 本地直启

可通过以下脚本启动：

```powershell
powershell -ExecutionPolicy Bypass -File deploy/start-local.ps1
```

用途：

- 本地开发
- 前后端联调
- 快速验证 Agent 主链路

### 2.2 容器栈启动

可通过以下脚本启动：

```powershell
powershell -ExecutionPolicy Bypass -File deploy/start-stack.ps1
```

用途：

- 本地或测试环境的一体化运行
- 验证向量库、监控和应用协同工作

---

## 3. 当前组件组成

当前默认包含以下组件：

- FastAPI 应用服务，默认端口 `8011`
- React + Vite 前端，构建产物位于 `frontend/dist`
- Qdrant，作为向量数据库
- Prometheus，用于抓取系统指标
- Grafana，用于查看监控面板

这意味着当前项目已经具备：

- 应用服务
- 前端页面
- 向量检索存储
- 最小监控能力

但这些能力还属于“生产化基础预留”，不是完整的生产方案。

---

## 4. 当前环境配置

建议从 `deploy/.env.example` 复制一份到 `deploy/.env`，再填写真实配置。

### 4.1 主要模型配置

- `LLM_PROVIDER=openai|minimax|fallback`
- `OPENAI_API_KEY`
- `MINIMAX_API_KEY`
- `MINIMAX_MODEL`
- `MINIMAX_BASE_URL`
- `AGENT_FORCE_FALLBACK`

MiniMax 当前使用官方 Anthropic 兼容端点：

- `MINIMAX_BASE_URL=https://api.minimaxi.com/anthropic`

### 4.2 向量检索配置

- `VECTOR_BACKEND=qdrant|local`
- `VECTOR_SERVICE_URL`
- `VECTOR_COLLECTION`
- `VECTOR_DIMENSIONS`

### 4.3 运行行为配置

- `ALLOW_ONLINE_SEARCH=true|false`
- `AGENT_TOOL_MAX_RETRIES`
- `AGENT_REPLAN_LIMIT`

说明：

- 真实密钥只应保存在 `deploy/.env`
- 不应把真实密钥提交到仓库

---

## 5. 当前可用的健康检查与监控入口

### 5.1 健康与运行时接口

- 应用健康：`GET /api/system/health`
- 运行时配置摘要：`GET /api/system/runtime`
- LLM 探测：`GET /api/system/llm-probe`

当 `perform_request=true` 且返回 `status=error` 时，可通过：

- `error_type`
- `error`
- `/api/system/health` 中的 `llm_last_error`

区分：

- 配置问题
- 上游网络问题
- 模型服务不可用问题

### 5.2 指标接口

- Metrics：`GET /api/system/metrics`

当前 Prometheus 默认抓取该接口。

---

## 6. 当前最小故障排查指南

### 6.1 LLM 提供方问题

若 `llm_probe` 返回 `status=error`，优先检查：

- API Key 是否存在
- Base URL 是否正确
- 模型名是否正确
- 外网访问是否可用

### 6.2 向量库问题

若记忆检索结果异常，优先检查：

- Qdrant 是否正常运行
- 向量集合是否存在
- 向量维度是否与当前 embedding 配置一致

### 6.3 工具调用失败

若工具执行超时或失败，优先检查：

- 工具是否已注册
- 远程服务是否可达
- 当前权限配置是否允许
- `/api/system/health` 是否已有相关报错

### 6.4 服务卡死或重启

建议处理顺序：

1. 停止当前服务
2. 检查是否存在卡住的任务状态或残留进程
3. 重新通过 `deploy/start-local.ps1` 或 `deploy/start-stack.ps1` 启动

---

## 7. 当前生产化不足

虽然项目已有部署与监控基础，但距离真正生产化仍有明显差距：

### 7.1 环境治理不足

- 环境分层不够完整
- 缺少更清晰的测试 / 预发 / 正式环境规范
- 缺少更正式的密钥治理流程

### 7.2 观测治理不足

- 指标覆盖仍偏基础
- 缺少更完整的业务指标
- 缺少统一告警规则

### 7.3 运维治理不足

- 缺少正式回滚流程
- 缺少备份恢复机制
- 缺少标准故障演练流程

### 7.4 组织级能力不足

- 当前仍偏单用户 / 单环境开发态
- 未建立权限、审计和多用户运行边界

---

## 8. 后续生产化建议

建议按以下顺序推进：

1. 环境配置分层
2. 指标、日志与告警补齐
3. 备份恢复方案
4. 发布与回滚流程
5. 多用户与权限体系接入

---

## 9. 当前统一结论

当前 Orion Agent 已经具备：

- 可本地运行
- 可容器化运行
- 可接入向量库
- 可暴露健康检查和指标接口

但它目前仍处于：

> “具备生产化基础预留，但尚未达到正式企业级生产部署完成态”的阶段

后续生产化工作应在执行内核稳定、会话与记忆治理收口后继续推进。

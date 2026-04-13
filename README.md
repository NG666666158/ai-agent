# Orion Agent MVP

这是基于《AI Agent 项目规划文档》落成的 MVP 实现，目标是跑通“任务输入 -> 计划生成 -> 步骤执行 -> 结构化结果输出”的单 Agent 闭环。

## 当前实现

- FastAPI 服务入口
- 任务、步骤、状态机数据模型
- Planner / Executor / Reflection 流程
- SQLite 持久化 Task Repository
- 带定义与调用日志的 Tool Registry
- 短期记忆与任务复核
- `POST /api/tasks`、`GET /api/tasks`、`GET /api/tasks/{task_id}`、`GET /api/tools` 接口

## 推荐开发节奏

1. 先把这版单机闭环跑通，验证数据结构、状态机和工具调用日志。
2. 再接入真实 LLM 和 Web 搜索工具。
3. 随后增加长期记忆、权限确认和前端可视化。

## 启动方式

```bash
python -m pip install -e .
python -m uvicorn --app-dir src orion_agent.main:app --reload
```

启动后可访问：

- `GET /healthz`
- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/steps`
- `POST /api/tasks/{task_id}/cancel`
- `GET /api/tools`

## 示例请求

```json
{
  "goal": "为一个 AI Agent 项目生成 MVP 开发方案",
  "constraints": [
    "聚焦文档和项目规划场景",
    "优先 Python FastAPI"
  ],
  "expected_output": "markdown",
  "source_text": "项目希望先完成单 Agent MVP，再逐步扩展记忆、工具和前端。"
}
```

## 当前 MVP 覆盖点

- 单任务执行闭环
- 任务解析
- 计划生成
- 4 个基础工具：文件读取、文本总结、关键词提取、Markdown 生成
- 简单短期记忆
- 任务状态与步骤展示
- 最终结果输出与基础复核

# Orion Agent 实施计划

## 项目切入点

根据现有项目文档，首版最适合选择“通用任务执行型 AI Agent”，但场景上先聚焦在文档与项目规划。这样可以用较少工具先验证 Agent 闭环，再逐步扩展到开发辅助和研究助理场景。

## 当前阶段目标

V0.1 原型版聚焦四件事：

1. 接收用户任务并结构化解析。
2. 自动生成可执行步骤。
3. 顺序执行步骤并保存状态。
4. 输出可交付的 Markdown 结果。

## 建议目录

```text
src/orion_agent/
  api/              # FastAPI 路由
  core/             # agent 核心流程
  main.py           # 服务入口
```

## 模块职责

- `models.py`：定义 Task、Step、状态枚举和请求响应结构。
- `planner.py`：将目标拆分为标准步骤。
- `executor.py`：按步骤推进执行，汇总中间结果。
- `tools.py`：注册和调用最小工具集合。
- `memory.py`：保留当前任务上下文，后续可扩展长期记忆。
- `agent.py`：编排 parse / plan / execute / reflect / deliver。

## 下一阶段优先级

1. 接入真实 LLM 和 Prompt 模板。
2. 增加文件读取、Markdown 生成、Web 搜索工具。
3. 引入 SQLite/PostgreSQL 持久化任务与步骤。
4. 为高风险工具动作加入权限确认机制。
5. 补充前端任务时间线和结果展示页。

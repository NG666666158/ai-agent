# Ralph 自动化执行说明

本文档说明如何在当前 `Orion Agent` 项目中使用本地化后的 Ralph 自动执行入口。

## 1. 已接入内容

当前项目已经新增以下文件：

- [scripts/ralph/ralph.ps1](/C:/github/ai-agent/ai-agent/scripts/ralph/ralph.ps1)
- [scripts/ralph/CLAUDE.md](/C:/github/ai-agent/ai-agent/scripts/ralph/CLAUDE.md)
- [scripts/ralph/prompt.md](/C:/github/ai-agent/ai-agent/scripts/ralph/prompt.md)
- [scripts/ralph/prd.json](/C:/github/ai-agent/ai-agent/scripts/ralph/prd.json)
- [scripts/ralph/progress.txt](/C:/github/ai-agent/ai-agent/scripts/ralph/progress.txt)

这套文件不是简单复制示例，而是针对当前项目做了本地适配：

- 默认优先使用 `claude.exe`
- 不依赖 `jq`
- 适配 Windows PowerShell
- 质量检查命令已对接当前项目
- 已把 `US-001` 标记为完成，自动化从 `US-002` 开始

## 2. 运行方式

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ralph/ralph.ps1 -Tool claude -MaxIterations 3
```

含义：

- `-Tool claude`：使用本机已安装的 Claude Code CLI
- `-MaxIterations 3`：最多自动执行 3 个 story 迭代

建议第一次先从 `1` 或 `2` 开始，确认行为符合预期后再放大迭代次数。

## 3. 执行流程

Ralph 运行器会：

1. 读取 `scripts/ralph/prd.json`
2. 确认目标分支 `ralph/orion-agent-enterprise-evolution`
3. 读取 `scripts/ralph/progress.txt`
4. 让 Claude 每轮只处理一个 `passes: false` 的最高优先级 story
5. 要求其运行最小质量检查
6. 要求其更新 `scripts/ralph/prd.json`
7. 要求其追加进度到 `scripts/ralph/progress.txt`
8. 如果全部 story 完成，则输出 `<promise>COMPLETE</promise>`

## 4. 当前状态

当前自动化队列的起点是：

- `US-002 细化执行阶段与恢复痕迹`

因为：

- `US-001` 已经手工完成并通过最小验证
- 该状态已写入 `scripts/ralph/prd.json` 和 `scripts/ralph/progress.txt`

## 5. 建议使用方式

建议按下面方式使用 Ralph：

1. 先运行 1 轮：
   `powershell -ExecutionPolicy Bypass -File scripts/ralph/ralph.ps1 -Tool claude -MaxIterations 1`
2. 检查生成的代码、提交和 `progress.txt`
3. 如果结果稳定，再运行 2 到 3 轮

## 6. 注意事项

- Ralph 是“每轮一个 story”的自动循环，不适合一次放很多大任务。
- 当前项目仍有不少历史乱码文档，后续自动化更适合优先处理结构清晰的 story。
- 如果自动化执行过程中质量检查失败，story 不应标记为完成。
- 运行前建议先确保工作区没有你不希望被自动提交的临时改动。

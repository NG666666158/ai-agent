# AI Agent MVP 测试报告

## 执行信息

- 执行时间：`2026-04-14T23:46:40`
- 执行方式：`docker run --rm -v C:\github\ai-agent\ai-agent:/app -w /app deploy-orion-agent python -m unittest discover -s tests -p test_*.py`
- 当前目录：`C:\github\ai-agent\ai-agent`
- 退出码：`0`

## 通过率统计

- 测试总数：`64`
- 通过数：`64`
- 失败数：`0`
- 错误数：`0`
- 通过率：`100.00%`

## 覆盖率统计

- 核心测试文件覆盖率：`10/10` (`100.00%`)
- 黑盒业务场景覆盖率：`20/20` (`100.00%`)

## 说明

- 这里的“覆盖率”表示当前测试体系对目标测试文件与 20 个业务场景数据集的覆盖情况。
- 当前脚本尚未集成 `coverage.py`，因此没有输出 Python 行覆盖率。
- 如果后续需要行覆盖率，可以在 Docker 镜像中安装 `coverage` 后继续扩展本脚本。

## 原始测试输出（末尾节选）

```text
Agent MVP", "memory_scope": "default"}
.{"event": "task.run.start", "goal": "Generate a deliverable from a local document", "memory_scope": "default"}
{"event": "task.created", "task_id": "task_269a18a267", "goal": "Generate a deliverable from a local document"}
{"event": "task.completed", "task_id": "task_269a18a267", "status": "COMPLETED", "steps": 6}
{"event": "task.run.success", "elapsed_ms": 20.86, "goal": "Generate a deliverable from a local document", "memory_scope": "default"}
.{"event": "task.run.start", "goal": "Generate project brief", "memory_scope": "default"}
{"event": "task.created", "task_id": "task_11f37fff3f", "goal": "Generate project brief"}
{"event": "task.completed", "task_id": "task_11f37fff3f", "status": "COMPLETED", "steps": 5}
{"event": "task.run.success", "elapsed_ms": 6.55, "goal": "Generate project brief", "memory_scope": "default"}
.{"event": "task.created", "task_id": "task_3f62b02b2b", "goal": "Stream task progress for the UI"}
{"event": "task.completed", "task_id": "task_3f62b02b2b", "status": "COMPLETED", "steps": 5}
.{"event": "task.run.start", "goal": "Implement AI Agent MVP", "memory_scope": "default"}
{"event": "task.created", "task_id": "task_fb108c7beb", "goal": "Implement AI Agent MVP"}
{"event": "task.completed", "task_id": "task_fb108c7beb", "status": "COMPLETED", "steps": 6}
{"event": "task.run.success", "elapsed_ms": 8.92, "goal": "Implement AI Agent MVP", "memory_scope": "default"}
.{"event": "task.run.start", "goal": "Generate a deliverable from a local document", "memory_scope": "default"}
{"event": "task.created", "task_id": "task_cefc8b990b", "goal": "Generate a deliverable from a local document"}
{"event": "task.completed", "task_id": "task_cefc8b990b", "status": "COMPLETED", "steps": 6}
{"event": "task.run.success", "elapsed_ms": 20.36, "goal": "Generate a deliverable from a local document", "memory_scope": "default"}
.{"event": "task.run.start", "goal": "Prepare AI Agent roadmap", "memory_scope": "roadmap"}
{"event": "task.created", "task_id": "task_e50eb5de8e", "goal": "Prepare AI Agent roadmap"}
{"event": "task.completed", "task_id": "task_e50eb5de8e", "status": "COMPLETED", "steps": 5}
{"event": "task.run.success", "elapsed_ms": 7.58, "goal": "Prepare AI Agent roadmap", "memory_scope": "roadmap"}
.{"event": "task.run.start", "goal": "Generate project brief", "memory_scope": "default"}
{"event": "task.created", "task_id": "task_2c196f242f", "goal": "Generate project brief"}
{"event": "task.completed", "task_id": "task_2c196f242f", "status": "COMPLETED", "steps": 5}
{"event": "task.run.success", "elapsed_ms": 5.74, "goal": "Generate project brief", "memory_scope": "default"}
.{"event": "task.run.start", "goal": "生成一个需要修订后再通过的交付结果", "memory_scope": "default"}
{"event": "task.created", "task_id": "task_799fdef565", "goal": "生成一个需要修订后再通过的交付结果"}
{"event": "task.completed", "task_id": "task_799fdef565", "status": "COMPLETED", "steps": 5}
{"event": "task.run.success", "elapsed_ms": 10.16, "goal": "生成一个需要修订后再通过的交付结果", "memory_scope": "default"}
.{"event": "task.run.start", "goal": "Evaluate AI Agent MVP output", "memory_scope": "default"}
{"event": "task.created", "task_id": "task_83467ac2a1", "goal": "Evaluate AI Agent MVP output"}
{"event": "task.completed", "task_id": "task_83467ac2a1", "status": "COMPLETED", "steps": 5}
{"event": "task.run.success", "elapsed_ms": 7.43, "goal": "Evaluate AI Agent MVP output", "memory_scope": "default"}
.{"event": "task.run.start", "goal": "Prepare frontend dashboard plan", "memory_scope": "semantic"}
{"event": "task.created", "task_id": "task_a423bc8a7d", "goal": "Prepare frontend dashboard plan"}
{"event": "task.completed", "task_id": "task_a423bc8a7d", "status": "COMPLETED", "steps": 5}
{"event": "task.run.success", "elapsed_ms": 7.26, "goal": "Prepare frontend dashboard plan", "memory_scope": "semantic"}
{"event": "task.run.start", "goal": "Document memory retrieval design", "memory_scope": "semantic"}
{"event": "task.created", "task_id": "task_ecc419ac9f", "goal": "Document memory retrieval design"}
{"event": "task.completed", "task_id": "task_ecc419ac9f", "status": "COMPLETED", "steps": 5}
{"event": "task.run.success", "elapsed_ms": 12.0, "goal": "Document memory retrieval design", "memory_scope": "semantic"}
.{"event": "task.created", "task_id": "task_528b7c9168", "goal": "Show streaming progress in Chinese UI"}
{"event": "task.completed", "task_id": "task_528b7c9168", "status": "COMPLETED", "steps": 5}
...{"event": "task.run.start", "goal": "Implement AI Agent MVP", "memory_scope": "default"}
{"event": "task.created", "task_id": "task_dc9320f599", "goal": "Implement AI Agent MVP"}
{"event": "task.completed", "task_id": "task_dc9320f599", "status": "COMPLETED", "steps": 6}
{"event": "task.run.success", "elapsed_ms": 14.39, "goal": "Implement AI Agent MVP", "memory_scope": "default"}
.......................................
----------------------------------------------------------------------
Ran 64 tests in 5.101s

OK

```

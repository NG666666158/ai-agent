# Orion Agent 连续开发清单

> 状态说明：本文档属于历史阶段的 story 映射清单，保留作为执行记录参考。当前统一开发顺序请以 [next-development-checklist.md](C:/github/ai-agent/ai-agent/docs/next-development-checklist.md) 为准。

本文档将 [tasks/prd-orion-agent-enterprise-evolution.md](/C:/github/ai-agent/ai-agent/tasks/prd-orion-agent-enterprise-evolution.md) 与 [tasks/prd-orion-agent-enterprise-evolution.json](/C:/github/ai-agent/ai-agent/tasks/prd-orion-agent-enterprise-evolution.json) 中的 stories 映射为可连续执行的开发清单，方便人工开发、AI 辅助开发或 Ralph 风格的逐 story 执行。

## 一、执行原则

- 每次只处理一个 story，避免跨越过多模块导致上下文失控。
- 先做“后端主数据结构与执行内核”，再做“RAG 与跨会话记忆”，最后做“前端体验、文档和生产化基础”。
- 每完成一个 story，都要补最小验证，再进入下一个 story。
- 如果 story 已部分完成，则优先做“收尾、统一主实现、补测试”，而不是重复开发。

## 二、推荐执行顺序

### Phase 1：主链路统一与恢复能力

1. `US-001 统一执行主链路数据模型`
交付物：
- 统一 `execution_nodes` 输出
- 执行节点构建测试
- 前端主视图切换到统一节点源

2. `US-002 细化执行阶段与恢复痕迹`
交付物：
- 更细颗粒的阶段枚举
- 失败分类规范
- 恢复事件前端展示字段

3. `US-003 实现可恢复的重规划流`
交付物：
- 跳过失败步骤继续执行
- 仅重建后半段计划
- 恢复回归测试

### Phase 2：RAG、记忆与画像主链路

4. `US-004 增强记忆元数据与最小混合召回`
交付物：
- `memory_type`
- `retrieval_score / retrieval_reason / retrieval_channels`
- 最小 hybrid recall + rerank
- 语义召回测试修通

5. `US-005 补齐跨会话记忆与用户画像注入`
交付物：
- 偏好提取器稳定化
- 新会话自动注入画像
- 回答来源命中提示增强

6. `US-006 支持画像编辑与冲突合并`
交付物：
- 画像编辑接口和页面
- 冲突合并动作
- 来源与状态展示

### Phase 3：前端 Agent 体验升级

7. `US-007 重构控制台为标准 Agent 对话布局`
交付物：
- 左侧会话栏
- 右侧当前对话与回答
- 折叠式思考过程

8. `US-008 升级前端执行过程可视化`
交付物：
- 执行时间线 / 节点流
- query 改写、检索、召回、Prompt 拼接、工具调用、恢复、回答生成节点
- 节点展开详情

9. `US-009 升级回答区 Markdown 与来源锚点`
交付物：
- 稳定 Markdown 渲染
- 段落内锚点
- 来源脚注跳转
- 复制回答按钮

### Phase 4：文档、平台化与运行基础

10. `US-010 清理中文文档并统一项目认知`
交付物：
- 中文 README
- 中文架构文档
- 中文路线图
- 中文测试报告模板

11. `US-011 补强多用户隔离与权限基础`
交付物：
- 数据模型预留 `user_id`
- 查询过滤能力
- 高风险权限基础

12. `US-012 补齐生产部署与运行观测基础`
交付物：
- 部署文档
- 运行观测说明
- 最小故障排查手册

## 三、建议按批次连续执行

### 批次 A：最小可见价值

- US-001
- US-002
- US-008
- US-009

适用目标：
- 尽快让前端看起来像成熟 Agent 产品
- 尽快把“系统到底做了什么”可视化出来

### 批次 B：记忆与跨会话稳定性

- US-004
- US-005
- US-006

适用目标：
- 解决“新开窗口就忘记用户”的核心体验问题
- 让画像与记忆链路更稳、更可控

### 批次 C：工程化收尾

- US-003
- US-010
- US-011
- US-012

适用目标：
- 提升恢复能力、项目认知一致性和后续平台化基础

## 四、每个 story 的标准执行模板

1. 阅读相关代码和现有文档。
2. 确认该 story 是否已有部分实现。
3. 只补当前 story 必要代码，避免顺手扩 scope。
4. 编写或修复对应测试。
5. 运行最小验证：
   - 后端相关：`python tests\\scripts\\run_all_tests_and_report.py` 或针对性 unittest
   - 前端相关：`cd frontend && npm run build`
6. 更新文档或清单状态。
7. 再进入下一个 story。

## 五、建议立刻启动的下一组任务

如果你要继续让系统更接近“企业级 Agent 可视化工作台”，推荐直接从下面 4 个 story 开始：

1. `US-001`：统一执行主链路数据模型
2. `US-002`：细化执行阶段与恢复痕迹
3. `US-008`：升级前端执行过程可视化
4. `US-009`：升级回答区 Markdown 与来源锚点

这 4 项完成后，你的项目会先得到最明显的产品体验提升，也更方便后续继续接入 Ralph 风格的 story 自动执行。

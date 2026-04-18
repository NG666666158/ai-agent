# Orion Agent 文档体系说明

## 1. 文档目的

本文档用于说明：

- 哪些文档是当前现行主文档
- 哪些文档属于历史阶段性文档
- 哪些文档是专题参考文档

从 `2026-04-18` 起，后续所有开发、评审和重构，优先以本文档列出的“现行主文档”作为统一基线。

---

## 2. 现行主文档

以下文档构成当前项目的主文档体系。

### 2.1 项目总入口

- [README.md](C:/github/ai-agent/ai-agent/README.md)

用途：

- 给新进入项目的人快速说明项目定位、当前能力、启动方式和下一步方向

### 2.2 当前真实完成度

- [current-progress-baseline.md](C:/github/ai-agent/ai-agent/docs/current-progress-baseline.md)

用途：

- 说明项目目前哪些已经完成、哪些部分完成、哪些还没开始

### 2.3 当前架构说明

- [current-architecture.md](C:/github/ai-agent/ai-agent/docs/current-architecture.md)

用途：

- 描述当前真实主架构、唯一主实现和当前核心模块边界

### 2.4 项目起源与演进记录

- [project-origin-and-evolution.md](C:/github/ai-agent/ai-agent/docs/project-origin-and-evolution.md)

用途：

- 固定最初需求、核心初心和项目从 MVP 演进到现在的轨迹

### 2.5 产品路线图

- [product-roadmap.md](C:/github/ai-agent/ai-agent/docs/product-roadmap.md)

用途：

- 说明当前项目从原型平台继续往产品平台演进的阶段目标

### 2.6 企业级稳定性路线

- [enterprise-stability-roadmap-v1.md](C:/github/ai-agent/ai-agent/docs/enterprise-stability-roadmap-v1.md)

用途：

- 说明如何把执行内核继续推进到接近 OpenClaw / claw code 思路的稳定性骨架

### 2.7 后续开发清单

- [next-development-checklist.md](C:/github/ai-agent/ai-agent/docs/next-development-checklist.md)

用途：

- 给后续开发提供 P0 / P1 / P2 的执行清单

### 2.8 生产部署说明

- [production.md](C:/github/ai-agent/ai-agent/docs/production.md)

用途：

- 说明当前部署形态、环境配置和生产化不足

---

## 3. 历史阶段文档

以下文档保留，但不再作为唯一基线使用。

### 3.1 `implementation-plan.md`

定位：

- 历史阶段实施计划

说明：

- 反映的是某一轮阶段性实施重点
- 当前应以“当前真实完成度基线”和“后续开发清单”为准

### 3.2 `continuous-development-checklist.md`

定位：

- 某一轮故事化开发清单映射文档

说明：

- 可作为连续开发的历史记录参考
- 不应替代当前统一路线图

### 3.3 `claw-aligned-refactor-checklist.md`

定位：

- 对齐 claw code 思路的一轮实施清单

说明：

- 当前其主体内容已经基本落地
- 后续应更多作为“已完成重构记录”和专题参考，而不是主计划入口

### 3.4 `execution-kernel-plan.md`

定位：

- 执行内核某一轮增强计划

说明：

- 可作为局部专题背景
- 当前总基线应由主文档体系统一承接

---

## 4. 专题参考文档

以下文档主要用于专题背景，不作为总线文档。

### 4.1 `toolpool-and-citation-extension-points.md`

用途：

- ToolPool 与 CitationMap 扩展点说明

### 4.2 `ralph-automation.md`

用途：

- Ralph 自动化执行相关说明

---

## 5. 文档使用顺序

如果是新同学或新一轮开发，建议按这个顺序阅读：

1. [README.md](C:/github/ai-agent/ai-agent/README.md)
2. [project-origin-and-evolution.md](C:/github/ai-agent/ai-agent/docs/project-origin-and-evolution.md)
3. [current-progress-baseline.md](C:/github/ai-agent/ai-agent/docs/current-progress-baseline.md)
4. [current-architecture.md](C:/github/ai-agent/ai-agent/docs/current-architecture.md)
5. [enterprise-stability-roadmap-v1.md](C:/github/ai-agent/ai-agent/docs/enterprise-stability-roadmap-v1.md)
6. [next-development-checklist.md](C:/github/ai-agent/ai-agent/docs/next-development-checklist.md)

---

## 6. 当前统一结论

从现在开始，项目文档的统一口径是：

- 最初目标：做一个中文、可视化、可追溯的 Agent 工作台
- 当前阶段：已经完成原型平台主体建设，正在推进平台化运行时内核
- 后续方向：把执行内核逐步提升到接近 OpenClaw / claw code 这类企业级稳定性思路，同时保留 Web 产品形态

任何新文档如果与这个口径冲突，应以现行主文档体系为准。

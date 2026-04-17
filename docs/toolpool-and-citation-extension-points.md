# ToolPool and Citation Extension Points

> 状态：完成 | 优先级：P1

本文档描述 Orion Agent 运行时扩展点的结构和用法，供平台维护者和插件开发者参考。

---

## ToolPool 扩展表面

### 工具元数据结构

`ToolDefinition` 是工具的元数据模型，位于 `src/orion_agent/core/models.py`：

```python
class ToolDefinition(BaseModel):
    name: str                           # 工具内部名称（唯一标识）
    description: str                    # 工具功能描述
    input_schema: dict[str, str]       # 输入参数类型
    output_schema: dict[str, str]       # 输出字段类型
    timeout_ms: int = 15_000           # 超时时间（毫秒）
    permission_level: ToolPermission    # SAFE / CONFIRM / RESTRICTED
    max_retries: int = 0               # 最大重试次数

    # --- P1 扩展字段 ---
    category: str | None = None         # 工具类别，如 "search", "file", "generation"
    display_name: str | None = None     # UI 显示全名
    display_label: str | None = None   # UI 短标签
```

### 工具类别

已定义的类别（可在 `ToolRegistry._definitions` 中查看）：

| category | 含义 | 示例工具 |
|----------|------|----------|
| `search` | 联网搜索 | `web_search` |
| `file` | 文件读写 | `read_local_file` |
| `text` | 文本处理 | `summarize_text` |
| `analysis` | 分析类 | `extract_keywords` |
| `generation` | 内容生成 | `generate_markdown` |

### 权限级别

| 级别 | 含义 | UI 行为 |
|------|------|---------|
| `SAFE` | 安全工具，无需确认 | 自动执行 |
| `CONFIRM` | 需要用户确认 | 显示确认对话框 |
| `RESTRICTED` | 高风险工具 | 需要额外授权 |

### 扩展方式

在 `src/orion_agent/core/tools.py` 的 `ToolRegistry.__init__` 中向 `self._definitions` 添加新条目：

```python
"my_tool": ToolDefinition(
    name="my_tool",
    description="我的自定义工具",
    input_schema={"input": "string"},
    output_schema={"result": "string"},
    category="custom",
    display_name="我的自定义工具",
    display_label="自定义",
    permission_level=ToolPermission.SAFE,
),
```

### 预留字段

- `category` / `display_name` / `display_label` 允许为 `None`，前端可据此决定是否显示标签。

---

## Citation Map 扩展表面

### 核心模型

citation map 位于 `src/orion_agent/core/models.py`：

```python
class CitationSource(BaseModel):
    id: str              # 唯一标识
    kind: str            # 来源类型，见下表
    label: str           # 显示用标签
    detail: str          # 详细描述
    source_record_id: str | None = None   # 源记录 ID
    source_session_id: str | None = None  # 所属会话
    source_task_id: str | None = None     # 产出该来源的任务
    excerpt: str | None = None            # 引用摘录

class ParagraphCitation(BaseModel):
    id: str
    paragraph_index: int            # 段落序号（0起始）
    paragraph_text: str             # 段落文本
    source_ids: list[str]          # 涉及的来源 ID 列表
    source_labels: list[str]       # 平行列表：对应来源的显示标签
```

### 已知 Citation Kind

在 `src/orion_agent/core/citation_map.py` 中定义：

| kind | 含义 |
|------|------|
| `memory` | 长期记忆召回 |
| `profile` | 用户画像事实 |
| `session_message` | 会话消息 |
| `source_summary` | 外部材料摘要 |
| `web_search` | 网络搜索结果 |
| `file` | 本地文件内容 |

### CitationMap Helper

`CitationMap`（`src/orion_agent/core/citation_map.py`）提供了类型化的引用地图构建接口：

```python
map = CitationMap()
source_id = map.add_source(
    kind="memory",
    label="用户偏好",
    detail="用户偏好中文回答",
    source_record_id="fact_123",
)
map.add_paragraph(
    paragraph_index=0,
    paragraph_text="用户希望用中文回答。",
    source_ids=[source_id],
    source_labels=["用户偏好"],
)
```

### 扩展方式

添加新的 `CitationSource.kind` 值：

1. 在 `citation_map.py` 的 `CITATION_KINDS` 字典中注册标签
2. 调用 `CitationMap.add_source(kind="my_plugin_kind", ...)` 注册来源
3. 通过 `source_task_id` 实现跨任务溯源

---

## 扩展检查清单

新增工具类别时：
- [ ] 在 `ToolDefinition.category` 中填写合适的类别
- [ ] 提供 `display_name` 和 `display_label` 供 UI 使用
- [ ] 确认 `permission_level` 与工具风险匹配

新增 Citation Kind 时：
- [ ] 在 `CITATION_KINDS` 中注册标签
- [ ] 在 `source_task_id` 中填写来源任务（支持溯源）
- [ ] 更新本文档的 kind 表格

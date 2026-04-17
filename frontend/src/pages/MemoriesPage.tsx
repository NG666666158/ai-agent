import { useEffect, useState } from "react";

import {
  deleteMemory,
  listMemories,
  updateMemory,
  type MemoryRecord,
  type MemoryUpdatePayload,
} from "../api";

type DraftMap = Record<string, { topic: string; scope: string; summary: string; details: string; tags: string }>;

function formatSource(memory: MemoryRecord) {
  const segments = [
    `来源类型：${memory.source.source_type || "未知"}`,
    memory.source.task_id ? `任务：${memory.source.task_id}` : "",
    memory.source.session_id ? `会话：${memory.source.session_id}` : "",
    memory.source.message_id ? `消息：${memory.source.message_id}` : "",
  ].filter(Boolean);
  return segments.join(" | ");
}

export function MemoriesPage() {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("");
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [drafts, setDrafts] = useState<DraftMap>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [statusText, setStatusText] = useState("正在加载记忆列表...");

  const loadMemories = async () => {
    setStatusText("正在加载记忆列表...");
    const items = await listMemories(scope, query, 80);
    setMemories(items);
    setDrafts(
      Object.fromEntries(
        items.map((item) => [
          item.id,
          {
            topic: item.topic,
            scope: item.scope,
            summary: item.summary,
            details: item.details,
            tags: item.tags.join(", "),
          },
        ]),
      ),
    );
    setStatusText(items.length ? `已找到 ${items.length} 条记忆。` : "当前没有匹配的记忆。");
  };

  const removeMemory = async (memoryId: string) => {
    await deleteMemory(memoryId);
    if (editingId === memoryId) {
      setEditingId(null);
    }
    await loadMemories();
  };

  const saveMemory = async (memoryId: string) => {
    const draft = drafts[memoryId];
    if (!draft) {
      return;
    }
    const payload: MemoryUpdatePayload = {
      topic: draft.topic.trim(),
      scope: draft.scope.trim() || "default",
      summary: draft.summary.trim(),
      details: draft.details.trim(),
      tags: draft.tags
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    };
    await updateMemory(memoryId, payload);
    setEditingId(null);
    await loadMemories();
  };

  useEffect(() => {
    void loadMemories();
  }, []);

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>记忆管理页</h2>
          <div className="meta">查看、搜索、编辑和软删除长期记忆，同时追溯来源与版本历史。</div>
        </div>
        <button className="secondary" onClick={() => void loadMemories()}>
          刷新记忆
        </button>
      </div>

      <div className="actions">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="按主题、摘要、详情或标签搜索" />
        <input value={scope} onChange={(event) => setScope(event.target.value)} placeholder="按作用域过滤，例如 default" />
        <button onClick={() => void loadMemories()}>搜索记忆</button>
      </div>

      <div className="meta" style={{ marginTop: 12 }}>
        {statusText}
      </div>

      <div className="list" style={{ marginTop: 16 }}>
        {memories.map((memory) => {
          const draft = drafts[memory.id];
          const isEditing = editingId === memory.id;

          return (
            <article className="card" key={memory.id}>
              <div className="tool-card-head">
                <div>
                  <h3>{memory.topic}</h3>
                  <div className="meta">
                    {memory.scope} | {new Date(memory.created_at).toLocaleString("zh-CN")}
                  </div>
                  <div className="meta">{formatSource(memory)}</div>
                </div>
                <div className="timeline-actions">
                  {isEditing ? (
                    <button onClick={() => void saveMemory(memory.id)}>保存修改</button>
                  ) : (
                    <button className="secondary" onClick={() => setEditingId(memory.id)}>
                      编辑记忆
                    </button>
                  )}
                  <button className="secondary" onClick={() => void removeMemory(memory.id)}>
                    删除记忆
                  </button>
                </div>
              </div>

              {isEditing && draft ? (
                <div className="task-form" style={{ marginTop: 16 }}>
                  <label>
                    主题
                    <input
                      value={draft.topic}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [memory.id]: { ...current[memory.id], topic: event.target.value },
                        }))
                      }
                    />
                  </label>
                  <label>
                    作用域
                    <input
                      value={draft.scope}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [memory.id]: { ...current[memory.id], scope: event.target.value },
                        }))
                      }
                    />
                  </label>
                  <label>
                    标签
                    <input
                      value={draft.tags}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [memory.id]: { ...current[memory.id], tags: event.target.value },
                        }))
                      }
                      placeholder="多个标签用逗号分隔"
                    />
                  </label>
                  <label>
                    摘要
                    <textarea
                      rows={4}
                      value={draft.summary}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [memory.id]: { ...current[memory.id], summary: event.target.value },
                        }))
                      }
                    />
                  </label>
                  <label>
                    详情
                    <textarea
                      rows={8}
                      value={draft.details}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [memory.id]: { ...current[memory.id], details: event.target.value },
                        }))
                      }
                    />
                  </label>
                </div>
              ) : (
                <>
                  <div className="tag-row">
                    {memory.tags.map((tag) => (
                      <span className="tool-badge" key={tag}>
                        {tag}
                      </span>
                    ))}
                  </div>
                  <pre>{memory.summary}</pre>
                  <details className="detail-toggle">
                    <summary>查看来源与版本历史</summary>
                    <div className="detail-body">
                      <pre>{formatSource(memory)}</pre>
                      <div className="list">
                        {memory.versions.length ? (
                          memory.versions
                            .slice()
                            .sort((a, b) => b.version - a.version)
                            .map((version) => (
                              <article className="card" key={`${memory.id}-${version.version}`}>
                                <div className="tool-card-head">
                                  <strong>版本 {version.version}</strong>
                                  <span className="tool-badge">
                                    {new Date(version.updated_at).toLocaleString("zh-CN")}
                                  </span>
                                </div>
                                <div className="meta">更新人：{version.updated_by}</div>
                                <div className="meta">主题：{version.topic}</div>
                                <div className="tag-row">
                                  {version.tags.map((tag) => (
                                    <span className="tool-badge" key={`${version.version}-${tag}`}>
                                      {tag}
                                    </span>
                                  ))}
                                </div>
                                <pre>{version.summary}</pre>
                              </article>
                            ))
                        ) : (
                          <div className="meta">当前还没有历史版本。</div>
                        )}
                      </div>
                    </div>
                  </details>
                  <details className="detail-toggle">
                    <summary>查看完整详情</summary>
                    <pre>{memory.details}</pre>
                  </details>
                </>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

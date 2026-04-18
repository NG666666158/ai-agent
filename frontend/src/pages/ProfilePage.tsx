import { useEffect, useMemo, useState } from "react";

import {
  getUserProfile,
  mergeUserProfileFact,
  updateUserProfileFact,
  type UserProfileFact,
} from "../api";

type DraftMap = Record<
  string,
  {
    label: string;
    value: string;
    confidence: string;
    summary: string;
    status: "ACTIVE" | "MERGED" | "ARCHIVED";
  }
>;

function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN");
}

function buildDrafts(items: UserProfileFact[]): DraftMap {
  return Object.fromEntries(
    items.map((item) => [
      item.id,
      {
        label: item.label,
        value: item.value,
        confidence: String(item.confidence),
        summary: item.summary,
        status: item.status,
      },
    ]),
  );
}

function statusLabel(status: UserProfileFact["status"]) {
  if (status === "ACTIVE") return "生效中";
  if (status === "MERGED") return "已合并";
  return "已归档";
}

export function ProfilePage() {
  const [facts, setFacts] = useState<UserProfileFact[]>([]);
  const [drafts, setDrafts] = useState<DraftMap>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  const [mergeSourceId, setMergeSourceId] = useState<string>("");
  const [mergeTargetId, setMergeTargetId] = useState<string>("");
  const [statusText, setStatusText] = useState("正在加载用户画像...");

  const loadFacts = async () => {
    setStatusText("正在加载用户画像...");
    const items = await getUserProfile(80, true);
    setFacts(items);
    setDrafts(buildDrafts(items));
    setStatusText(items.length ? `已加载 ${items.length} 条画像事实，可继续编辑和合并。` : "当前还没有沉淀下来的用户画像。");
  };

  const groupedFacts = useMemo(() => {
    const groups = new Map<string, UserProfileFact[]>();
    for (const item of facts) {
      const current = groups.get(item.category) ?? [];
      current.push(item);
      groups.set(item.category, current);
    }
    return Array.from(groups.entries()).map(([category, items]) => ({
      category,
      items: items.slice().sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()),
    }));
  }, [facts]);

  const activeFacts = useMemo(() => facts.filter((item) => item.status === "ACTIVE"), [facts]);

  const saveFact = async (factId: string) => {
    const draft = drafts[factId];
    if (!draft) {
      return;
    }
    await updateUserProfileFact(factId, {
      label: draft.label.trim(),
      value: draft.value.trim(),
      confidence: Number.parseFloat(draft.confidence) || 0.8,
      summary: draft.summary.trim(),
      status: draft.status,
    });
    setEditingId(null);
    await loadFacts();
  };

  const handleMerge = async () => {
    if (!mergeSourceId || !mergeTargetId || mergeSourceId === mergeTargetId) {
      setStatusText("请选择两个不同的画像事实进行合并。");
      return;
    }
    await mergeUserProfileFact(mergeSourceId, {
      target_fact_id: mergeTargetId,
      summary: "该画像已在页面中手动合并，保留目标画像作为当前生效版本。",
    });
    setMergeSourceId("");
    setMergeTargetId("");
    await loadFacts();
  };

  useEffect(() => {
    void loadFacts();
  }, []);

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>用户画像与偏好</h2>
          <div className="meta">
            这里会展示跨会话沉淀下来的偏好事实。你可以手动修正、归档冲突项，并把重复画像合并成唯一主记录。
          </div>
        </div>
        <button className="secondary" onClick={() => void loadFacts()}>
          刷新画像
        </button>
      </div>

      <div className="metric-grid">
        <article className="metric-card">
          <span>画像总数</span>
          <strong>{facts.length}</strong>
        </article>
        <article className="metric-card">
          <span>当前生效</span>
          <strong>{activeFacts.length}</strong>
        </article>
        <article className="metric-card">
          <span>画像类别</span>
          <strong>{groupedFacts.length}</strong>
        </article>
      </div>

      <div className="meta">{statusText}</div>

      <section className="detail-section">
        <div className="detail-header-card">
          <div className="tool-card-head">
            <div>
              <h3>冲突合并</h3>
              <div className="meta">当同一类画像出现多条近义或重复事实时，可以保留一个主画像，将另一条合并进去。</div>
            </div>
          </div>
          <div className="actions" style={{ marginTop: 16 }}>
            <select
              value={mergeSourceId}
              onChange={(event) => setMergeSourceId(event.target.value)}
              style={{ minWidth: 240, padding: "12px 14px", borderRadius: 16 }}
            >
              <option value="">选择待合并画像</option>
              {facts.map((fact) => (
                <option key={`source-${fact.id}`} value={fact.id}>
                  {fact.label} / {fact.value} / {statusLabel(fact.status)}
                </option>
              ))}
            </select>
            <select
              value={mergeTargetId}
              onChange={(event) => setMergeTargetId(event.target.value)}
              style={{ minWidth: 240, padding: "12px 14px", borderRadius: 16 }}
            >
              <option value="">选择保留为主画像</option>
              {facts.map((fact) => (
                <option key={`target-${fact.id}`} value={fact.id}>
                  {fact.label} / {fact.value} / {statusLabel(fact.status)}
                </option>
              ))}
            </select>
            <button onClick={() => void handleMerge()}>执行合并</button>
          </div>
        </div>
      </section>

      <div className="list" style={{ marginTop: 16 }}>
        {groupedFacts.map((group) => (
          <article className="card" key={group.category}>
            <div className="tool-card-head">
              <div>
                <h3>{group.category}</h3>
                <div className="meta">同类画像会按更新时间排序，激活项会自动注入到新会话上下文中。</div>
              </div>
              <span className="tool-badge">{group.items.length} 条</span>
            </div>

            <div className="list" style={{ marginTop: 16 }}>
              {group.items.map((fact) => {
                const draft = drafts[fact.id];
                const isEditing = editingId === fact.id;
                return (
                  <article className="detail-header-card" key={fact.id}>
                    <div className="tool-card-head">
                      <div>
                        <h3>{fact.label}</h3>
                        <div className="meta">
                          值：{fact.value} | 置信度：{fact.confidence.toFixed(2)} | 状态：{statusLabel(fact.status)}
                        </div>
                        <div className="meta">
                          来源会话：{fact.source_session_id ?? "未知"} | 来源任务：{fact.source_task_id ?? "未知"}
                        </div>
                        <div className="meta">最近更新时间：{formatTime(fact.updated_at)}</div>
                        {fact.superseded_by ? <div className="meta">已被画像 {fact.superseded_by} 接替</div> : null}
                      </div>
                      <div className="timeline-actions">
                        {isEditing ? (
                          <button onClick={() => void saveFact(fact.id)}>保存画像</button>
                        ) : (
                          <button className="secondary" onClick={() => setEditingId(fact.id)}>
                            编辑画像
                          </button>
                        )}
                      </div>
                    </div>

                    {isEditing && draft ? (
                      <div className="task-form" style={{ marginTop: 16 }}>
                        <label>
                          标签
                          <input
                            value={draft.label}
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [fact.id]: { ...current[fact.id], label: event.target.value },
                              }))
                            }
                          />
                        </label>
                        <label>
                          值
                          <input
                            value={draft.value}
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [fact.id]: { ...current[fact.id], value: event.target.value },
                              }))
                            }
                          />
                        </label>
                        <label>
                          置信度
                          <input
                            value={draft.confidence}
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [fact.id]: { ...current[fact.id], confidence: event.target.value },
                              }))
                            }
                          />
                        </label>
                        <label>
                          状态
                          <select
                            value={draft.status}
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [fact.id]: {
                                  ...current[fact.id],
                                  status: event.target.value as "ACTIVE" | "MERGED" | "ARCHIVED",
                                },
                              }))
                            }
                            style={{ minWidth: 220, padding: "12px 14px", borderRadius: 16 }}
                          >
                            <option value="ACTIVE">生效中</option>
                            <option value="ARCHIVED">已归档</option>
                            <option value="MERGED">已合并</option>
                          </select>
                        </label>
                        <label>
                          说明
                          <textarea
                            rows={4}
                            value={draft.summary}
                            onChange={(event) =>
                              setDrafts((current) => ({
                                ...current,
                                [fact.id]: { ...current[fact.id], summary: event.target.value },
                              }))
                            }
                          />
                        </label>
                      </div>
                    ) : (
                      <pre>{fact.summary || `${fact.label}: ${fact.value}`}</pre>
                    )}
                  </article>
                );
              })}
            </div>
          </article>
        ))}

        {!facts.length ? (
          <div className="meta">先在控制台里进行几轮真实对话，例如“我想学 Java”，系统会逐步抽取并沉淀稳定偏好。</div>
        ) : null}
      </div>
    </section>
  );
}

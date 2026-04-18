import { useEffect, useMemo, useState } from "react";

import {
  createSession,
  getSession,
  listSessions,
  refreshSessionSummary,
  type ChatMessage,
  type Session,
  type SessionDetail,
  type Task,
} from "../api";

function roleLabel(role: ChatMessage["role"]) {
  const mapping = {
    USER: "用户",
    ASSISTANT: "助手",
    SYSTEM: "系统",
  };
  return mapping[role] ?? role;
}

function statusLabel(status: string) {
  const mapping: Record<string, string> = {
    CREATED: "已创建",
    PARSED: "已解析",
    PLANNED: "已规划",
    WAITING_APPROVAL: "等待确认",
    RUNNING: "执行中",
    WAITING_TOOL: "等待工具",
    REPLANNING: "重规划中",
    REFLECTING: "结果复核中",
    COMPLETED: "已完成",
    FAILED: "执行失败",
    CANCELLED: "已取消",
  };
  return mapping[status] ?? status;
}

function SessionTaskCard({ task }: { task: Task }) {
  return (
    <article className="card">
      <div className="tool-card-head">
        <strong>{task.title}</strong>
        <span className="tool-badge">{statusLabel(task.status)}</span>
      </div>
      <div className="meta">
        {task.id} | {new Date(task.updated_at).toLocaleString("zh-CN")}
      </div>
      <pre>{task.result ?? task.failure_message ?? "该任务暂时还没有结果。"}</pre>
    </article>
  );
}

export function SessionsPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState<SessionDetail | null>(null);
  const [statusText, setStatusText] = useState("正在加载会话列表...");
  const [branchTitle, setBranchTitle] = useState("");
  const [branchPrompt, setBranchPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadSessions = async (preferredId?: string) => {
    setStatusText("正在加载会话列表...");
    const items = await listSessions();
    setSessions(items);

    const targetId = preferredId ?? selected?.session.id ?? items[0]?.id;
    if (!targetId) {
      setSelected(null);
      setStatusText("当前还没有会话记录。");
      return;
    }

    const detail = await getSession(targetId);
    setSelected(detail);
    setStatusText(`已加载 ${items.length} 个会话。`);
  };

  const childSessions = useMemo(
    () => sessions.filter((item) => item.source_session_id && item.source_session_id === selected?.session.id),
    [selected?.session.id, sessions],
  );

  const handleRefreshSummary = async () => {
    if (!selected) {
      return;
    }
    setStatusText("正在刷新会话摘要...");
    const detail = await refreshSessionSummary(selected.session.id, true);
    setSelected(detail);
    setStatusText("会话摘要已刷新。");
    setSessions(await listSessions());
  };

  const handleBranch = async () => {
    if (!selected) {
      return;
    }
    setSubmitting(true);
    setStatusText("正在创建分支会话...");
    try {
      const created = await createSession({
        title: branchTitle.trim() || `${selected.session.title} - 分支续聊`,
        source_session_id: selected.session.id,
        seed_prompt: branchPrompt.trim() || undefined,
      });
      setBranchTitle("");
      setBranchPrompt("");
      await loadSessions(created.id);
      setStatusText("分支会话已创建，可以继续多轮续聊。");
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => {
    void loadSessions();
  }, []);

  return (
    <section className="grid">
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>会话历史</h2>
            <div className="meta">查看全部 chat session，回放消息、刷新摘要，并从任意会话继续分支续聊。</div>
          </div>
          <button className="secondary" onClick={() => void loadSessions()}>
            刷新会话
          </button>
        </div>

        <div className="meta" style={{ marginTop: 12 }}>
          {statusText}
        </div>

        <div className="list">
          {sessions.map((session) => (
            <article className="card clickable" key={session.id} onClick={() => void loadSessions(session.id)}>
              <h3>{session.title}</h3>
              <div className="meta">{session.id}</div>
              <div className="meta">
                消息数：{session.message_count} | {new Date(session.updated_at).toLocaleString("zh-CN")}
              </div>
              {session.source_session_id ? <div className="meta">分支来源：{session.source_session_id}</div> : null}
              {session.context_summary ? <pre>{session.context_summary}</pre> : null}
            </article>
          ))}
          {!sessions.length ? <div className="meta">当前还没有会话记录。</div> : null}
        </div>
      </section>

      <section className="panel">
        {selected ? (
          <>
            <div className="panel-head">
              <div>
                <h2>{selected.session.title}</h2>
                <div className="meta">
                  {selected.session.id} | 创建于 {new Date(selected.session.created_at).toLocaleString("zh-CN")}
                </div>
                {selected.session.source_session_id ? (
                  <div className="meta">这是从会话 {selected.session.source_session_id} 分支出来的续聊分支。</div>
                ) : null}
              </div>
              <div className="actions">
                <button className="secondary" onClick={() => void handleRefreshSummary()}>
                  刷新摘要
                </button>
              </div>
            </div>

            <section className="detail-section">
              <h3>多轮压缩摘要</h3>
              <pre>{selected.session.context_summary || "当前会话轮次较少，暂未生成压缩摘要。"}</pre>
              {selected.session.summary_updated_at ? (
                <div className="meta">摘要更新时间：{new Date(selected.session.summary_updated_at).toLocaleString("zh-CN")}</div>
              ) : null}
            </section>

            <section className="detail-section">
              <h3>分支续聊</h3>
              <div className="task-form">
                <label>
                  新会话标题
                  <input
                    value={branchTitle}
                    onChange={(event) => setBranchTitle(event.target.value)}
                    placeholder="例如：继续讨论发布方案"
                  />
                </label>
                <label>
                  续聊说明
                  <textarea
                    rows={4}
                    value={branchPrompt}
                    onChange={(event) => setBranchPrompt(event.target.value)}
                    placeholder="例如：保留前面的结论，重点展开实施步骤和风险控制。"
                  />
                </label>
                <div className="actions">
                  <button onClick={() => void handleBranch()} disabled={submitting}>
                    {submitting ? "创建中..." : "从当前会话分支"}
                  </button>
                </div>
              </div>

              {childSessions.length ? (
                <div className="list">
                  {childSessions.map((session) => (
                    <article className="card clickable" key={session.id} onClick={() => void loadSessions(session.id)}>
                      <h3>{session.title}</h3>
                      <div className="meta">
                        {session.id} | {new Date(session.updated_at).toLocaleString("zh-CN")}
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="meta">当前会话还没有分支会话。</div>
              )}
            </section>

            <section className="detail-section">
              <h3>消息回放</h3>
              <div className="list">
                {selected.messages.map((message) => (
                  <article className="card" key={message.id}>
                    <div className="tool-card-head">
                      <strong>{roleLabel(message.role)}</strong>
                      <span className="tool-badge">{new Date(message.created_at).toLocaleString("zh-CN")}</span>
                    </div>
                    {message.task_id ? <div className="meta">关联任务：{message.task_id}</div> : null}
                    <pre>{message.content}</pre>
                  </article>
                ))}
                {!selected.messages.length ? <div className="meta">当前会话还没有消息。</div> : null}
              </div>
            </section>

            <section className="detail-section">
              <h3>关联任务追溯</h3>
              <div className="list">
                {selected.tasks.map((task) => (
                  <SessionTaskCard key={task.id} task={task} />
                ))}
                {!selected.tasks.length ? <div className="meta">当前会话还没有关联任务。</div> : null}
              </div>
            </section>
          </>
        ) : (
          <div className="meta">请选择一个会话查看详情。</div>
        )}
      </section>
    </section>
  );
}

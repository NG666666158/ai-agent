import { useEffect, useState } from "react";

import {
  confirmTaskApproval,
  getTask,
  getTaskEvaluation,
  getTaskTrace,
  listTasks,
  type Evaluation,
  type ExecutionNode,
  type PendingApproval,
  type ReplanEvent,
  type Task,
  type TaskTrace,
  type ToolInvocation,
} from "../api";

function toChineseStatus(status: string) {
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
    SUCCESS: "成功",
    ERROR: "错误",
    TODO: "待处理",
    DOING: "处理中",
    DONE: "已完成",
    SKIPPED: "已跳过",
    RETRYING: "重试中",
  };
  return mapping[status] ?? status;
}

function toChineseFailure(category: string) {
  const mapping: Record<string, string> = {
    NONE: "无",
    INPUT_ERROR: "输入错误",
    NETWORK_ERROR: "网络错误",
    TOOL_TIMEOUT: "工具超时",
    TOOL_UNAVAILABLE: "工具不可用",
    PERMISSION_DENIED: "权限拒绝",
    VALIDATION_ERROR: "校验错误",
    REVIEW_FAILED: "结果评审未通过",
    INTERNAL_ERROR: "内部错误",
  };
  return mapping[category] ?? category;
}

function toChineseResolution(resolution: string) {
  const mapping: Record<string, string> = {
    NONE: "无恢复动作",
    RETRY_CURRENT_STEP: "重试当前步骤",
    SKIP_FAILED_STEP: "跳过失败步骤继续执行",
    REPLAN_REMAINING_STEPS: "只重建后半段计划",
    REPLAN_FROM_CHECKPOINT: "从检查点重规划",
    REQUIRE_USER_ACTION: "等待用户处理",
    FAIL_FAST: "快速失败",
  };
  return mapping[resolution] ?? resolution;
}

function toChineseNodeKind(kind: string) {
  const mapping: Record<string, string> = {
    query_rewrite: "Query 改写",
    prompt_assembly: "Prompt 拼接",
    vector_retrieval: "向量检索",
    multi_recall: "多路召回",
    progress: "系统进度",
    step: "执行步骤",
    tool: "工具调用",
    recovery: "恢复与重规划",
    answer_generation: "回答生成",
    review: "结果复核",
  };
  return mapping[kind] ?? kind;
}

function toChineseNodeStatus(status: string) {
  const mapping: Record<string, string> = {
    done: "已完成",
    doing: "进行中",
    error: "异常",
    todo: "待执行",
    skipped: "已跳过",
    retrying: "重试中",
  };
  return mapping[status] ?? status;
}

function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN");
}

function downloadFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function ApprovalCard({
  task,
  approval,
  onRefresh,
}: {
  task: Task;
  approval: PendingApproval;
  onRefresh: (nextTask?: Task) => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState(false);

  const decide = async (approved: boolean) => {
    setSubmitting(true);
    try {
      const updated = await confirmTaskApproval(task.id, approval.id, approved);
      await onRefresh(updated);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <article className="approval-card">
      <div className="approval-head">
        <div>
          <strong>{approval.operation}</strong>
          <div className="meta">{approval.tool_name}</div>
        </div>
        <span className="approval-badge">需要确认</span>
      </div>
      <p>{approval.message}</p>
      <div className="meta">{approval.risk_note}</div>
      <details className="detail-toggle" open>
        <summary>查看操作参数</summary>
        <pre>{JSON.stringify(approval.input_payload, null, 2)}</pre>
      </details>
      {approval.approved === null ? (
        <div className="actions">
          <button disabled={submitting} onClick={() => void decide(true)}>
            允许继续
          </button>
          <button className="secondary" disabled={submitting} onClick={() => void decide(false)}>
            拒绝操作
          </button>
        </div>
      ) : (
        <div className="meta">{approval.approved ? "该操作已经确认通过。" : "该操作已经被拒绝。"}</div>
      )}
    </article>
  );
}

function ToolInvocationCard({ item }: { item: ToolInvocation }) {
  return (
    <article className="tool-card">
      <div className="tool-card-head">
        <div>
          <strong>{item.tool_name}</strong>
          <div className="meta">
            第 {item.attempt_count} 次尝试 · {toChineseStatus(item.status)}
          </div>
        </div>
        <span className="tool-badge">{toChineseFailure(item.failure_category)}</span>
      </div>
      <div className="meta">
        开始时间：{formatTime(item.started_at)} | 完成时间：{formatTime(item.completed_at)}
      </div>
      <details className="detail-toggle">
        <summary>查看调用详情</summary>
        <div className="tool-columns">
          <div>
            <div className="meta">输入参数</div>
            <pre>{JSON.stringify(item.input_payload, null, 2)}</pre>
          </div>
          <div>
            <div className="meta">输出摘要</div>
            <pre>{item.output_preview ?? item.error ?? "暂无输出"}</pre>
          </div>
        </div>
      </details>
    </article>
  );
}

function RecoveryEventCard({ event }: { event: ReplanEvent }) {
  return (
    <article className="recovery-card">
      <div className="tool-card-head">
        <div>
          <strong>{event.summary}</strong>
          <div className="meta">
            触发时间：{formatTime(event.created_at)} | 原因：{event.reason}
          </div>
        </div>
        <span className="tool-badge">{toChineseFailure(event.failure_category)}</span>
      </div>
      <div className="meta">
        触发阶段：{event.trigger_phase} | 检查点：{event.checkpoint_stage ?? "未知"}
      </div>
      <div className="meta">
        恢复策略：{event.recovery_strategy} | 恢复起点：
        {event.resume_from_step_name ?? event.checkpoint_step_id ?? "未记录"}
      </div>
      {event.detail ? <pre>{event.detail}</pre> : null}
    </article>
  );
}

function ExecutionNodeTimeline({ nodes }: { nodes: ExecutionNode[] }) {
  if (!nodes.length) {
    return <div className="empty-note">当前任务还没有生成统一执行节点。</div>;
  }

  return (
    <div className="execution-node-list">
      {nodes.map((node) => (
        <article className={`execution-node-card execution-node-${node.status}`} key={node.id}>
          <div className="execution-node-head">
            <div>
              <div className="agent-section-kicker">{toChineseNodeKind(node.kind)}</div>
              <strong>{node.title}</strong>
            </div>
            <div className="execution-node-meta">
              <span className="tool-badge">{toChineseNodeStatus(node.status)}</span>
              <span>{node.started_at ? formatTime(node.started_at) : "暂无时间"}</span>
            </div>
          </div>
          <div className="meta">{node.summary}</div>
          {node.duration_ms != null ? <div className="meta">耗时 {node.duration_ms} ms</div> : null}
          {node.detail ? <pre>{node.detail}</pre> : null}
          {node.artifacts.length ? (
            <div className="execution-artifact-grid">
              {node.artifacts.map((artifact) => (
                <article className="thought-info-card" key={`${node.id}-${artifact.label}`}>
                  <strong>{artifact.label}</strong>
                  <pre>{artifact.content}</pre>
                </article>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

export function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [trace, setTrace] = useState<TaskTrace | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshTaskList = async (preferredId?: string) => {
    const taskItems = await listTasks();
    setTasks(taskItems);
    const targetId = preferredId ?? selectedTask?.id ?? taskItems[0]?.id;
    if (!targetId) {
      setSelectedTask(null);
      setEvaluation(null);
      setTrace(null);
      return;
    }
    const detailed = await getTask(targetId);
    setSelectedTask(detailed);
    setEvaluation(await getTaskEvaluation(targetId));
    setTrace(await getTaskTrace(targetId));
  };

  useEffect(() => {
    void (async () => {
      try {
        await refreshTaskList();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedTask || ["COMPLETED", "FAILED", "CANCELLED"].includes(selectedTask.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshTaskList(selectedTask.id);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [selectedTask?.id, selectedTask?.status]);

  const inspectTask = async (task: Task) => {
    setSelectedTask(await getTask(task.id));
    setEvaluation(await getTaskEvaluation(task.id));
    setTrace(await getTaskTrace(task.id));
  };

  const exportMarkdown = () => {
    if (!selectedTask?.result) {
      return;
    }
    downloadFile(`${selectedTask.id}.md`, selectedTask.result, "text/markdown;charset=utf-8");
  };

  const exportJson = () => {
    if (!selectedTask) {
      return;
    }
    downloadFile(`${selectedTask.id}.json`, JSON.stringify(selectedTask, null, 2), "application/json;charset=utf-8");
  };

  return (
    <section className="grid">
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>任务列表</h2>
            <div className="meta">查看最近任务，点击后进入右侧详情区域。</div>
          </div>
          <button className="secondary" onClick={() => void refreshTaskList()}>
            刷新列表
          </button>
        </div>
        <div className="list">
          {tasks.map((task) => (
            <article className="card clickable" key={task.id} onClick={() => void inspectTask(task)}>
              <h3>{task.title}</h3>
              <div className="meta">{toChineseStatus(task.status)}</div>
              <div className="meta">{task.id}</div>
              <div className="meta">统一节点数：{task.execution_nodes.length}</div>
              {task.pending_approvals.some((item) => item.approved === null) ? (
                <div className="task-inline-badge">待确认操作</div>
              ) : null}
              {task.checkpoint.last_failure_resolution !== "NONE" ? (
                <div className="task-inline-badge">
                  恢复：{toChineseResolution(task.checkpoint.last_failure_resolution)}
                </div>
              ) : null}
            </article>
          ))}
          {!tasks.length && !loading ? <div className="meta">当前还没有任务记录。</div> : null}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>任务详情页</h2>
            <div className="meta">优先展示统一执行节点，其余步骤、工具和追溯信息作为补充明细。</div>
          </div>
          {selectedTask ? (
            <div className="toolbar-actions">
              <button className="secondary" onClick={exportMarkdown}>
                导出 Markdown
              </button>
              <button className="secondary" onClick={exportJson}>
                导出 JSON
              </button>
            </div>
          ) : null}
        </div>

        {selectedTask ? (
          <>
            <div className="detail-header-card">
              <h3>{selectedTask.title}</h3>
              <div className="meta">
                {selectedTask.id} | {toChineseStatus(selectedTask.status)}
              </div>
              <div className="detail-stats">
                <article className="metric-card">
                  <span>质量评分</span>
                  <strong>{evaluation?.score?.toFixed(2) ?? "--"}</strong>
                </article>
                <article className="metric-card">
                  <span>统一节点</span>
                  <strong>{selectedTask.execution_nodes.length}</strong>
                </article>
                <article className="metric-card">
                  <span>恢复次数</span>
                  <strong>{selectedTask.checkpoint.recovery_attempt}</strong>
                </article>
                <article className="metric-card">
                  <span>重规划次数</span>
                  <strong>{selectedTask.replan_count}</strong>
                </article>
              </div>
              <div className="meta">
                创建时间：{formatTime(selectedTask.created_at)} | 更新时间：{formatTime(selectedTask.updated_at)}
              </div>
              <div className="meta">
                最近失败类型：{toChineseFailure(selectedTask.checkpoint.last_failure_category)}
                {selectedTask.failure_message ? ` | 失败说明：${selectedTask.failure_message}` : ""}
              </div>
            </div>

            <section className="detail-section">
              <h3>统一执行主链路</h3>
              <div className="meta">这里是 `execution_nodes` 的主展示区域，前端优先消费这套统一数据结构。</div>
              <ExecutionNodeTimeline nodes={selectedTask.execution_nodes} />
            </section>

            <section className="detail-section">
              <h3>恢复摘要</h3>
              <div className="recovery-summary-grid">
                <article className="recovery-summary-card">
                  <span>恢复策略</span>
                  <strong>{toChineseResolution(selectedTask.checkpoint.last_failure_resolution)}</strong>
                  <div className="meta">最近一次系统选择的恢复动作</div>
                </article>
                <article className="recovery-summary-card">
                  <span>恢复起点</span>
                  <strong>{selectedTask.checkpoint.last_recovery_step_name ?? "暂无"}</strong>
                  <div className="meta">系统从哪一步开始恢复或重建</div>
                </article>
                <article className="recovery-summary-card">
                  <span>最近完成步骤</span>
                  <strong>{selectedTask.checkpoint.last_completed_step_name ?? "暂无"}</strong>
                  <div className="meta">最近一次稳定完成的步骤</div>
                </article>
                <article className="recovery-summary-card">
                  <span>恢复备注</span>
                  <strong>{selectedTask.checkpoint.last_recovery_note ?? "暂无"}</strong>
                  <div className="meta">便于前端解释恢复链路</div>
                </article>
              </div>
            </section>

            {selectedTask.pending_approvals.some((item) => item.approved === null) ? (
              <section className="detail-section">
                <h3>高风险操作确认</h3>
                <div className="list">
                  {selectedTask.pending_approvals
                    .filter((item) => item.approved === null)
                    .map((approval) => (
                      <ApprovalCard
                        key={approval.id}
                        task={selectedTask}
                        approval={approval}
                        onRefresh={async (nextTask?: Task) => {
                          if (nextTask) {
                            setSelectedTask(nextTask);
                          }
                          await refreshTaskList(nextTask?.id ?? selectedTask.id);
                        }}
                      />
                    ))}
                </div>
              </section>
            ) : null}

            <section className="detail-section">
              <h3>最终结果</h3>
              <pre className="result">{selectedTask.result ?? "暂无结果输出"}</pre>
            </section>

            <section className="detail-section">
              <h3>恢复与重规划记录</h3>
              <div className="list">
                {selectedTask.replan_history.map((event) => (
                  <RecoveryEventCard event={event} key={event.id} />
                ))}
                {!selectedTask.replan_history.length ? <div className="meta">当前任务暂无重规划记录。</div> : null}
              </div>
            </section>

            <section className="detail-section">
              <h3>工具调用详情</h3>
              <div className="list">
                {selectedTask.tool_invocations.map((item) => (
                  <ToolInvocationCard item={item} key={item.id} />
                ))}
                {!selectedTask.tool_invocations.length ? <div className="meta">当前任务暂无工具调用记录。</div> : null}
              </div>
            </section>

            <section className="detail-section">
              <h3>历史追溯</h3>
              <div className="card">
                <div className="meta">
                  关联会话：{trace?.session?.session.title ?? "无"}{" "}
                  {trace?.session?.session.id ? `| ${trace.session.session.id}` : ""}
                </div>
                <div className="meta">
                  召回记忆数：{trace?.memory_ids.length ?? 0} | 工具调用数：{trace?.tool_count ?? 0}
                </div>
                <details className="detail-toggle">
                  <summary>查看会话消息回放</summary>
                  <div className="list" style={{ padding: 12 }}>
                    {trace?.session?.messages.map((message) => (
                      <article className="card" key={message.id}>
                        <div className="tool-card-head">
                          <strong>{message.role}</strong>
                          <span className="tool-badge">{formatTime(message.created_at)}</span>
                        </div>
                        <pre>{message.content}</pre>
                      </article>
                    ))}
                  </div>
                </details>
              </div>
            </section>

            <section className="detail-section">
              <h3>质量评估</h3>
              <div className="list">
                {(evaluation?.checks ?? []).map((item) => (
                  <article className="card" key={item}>
                    <pre>{item}</pre>
                  </article>
                ))}
              </div>
            </section>
          </>
        ) : (
          <div className="meta">请选择一个任务查看详情。</div>
        )}
      </section>
    </section>
  );
}

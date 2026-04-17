import { Fragment, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import {
  confirmTaskApproval,
  createSession,
  getSession,
  launchTask,
  listSessions,
  listTasks,
  streamTask,
  type ExecutionNode,
  type PendingApproval,
  type Session,
  type SessionDetail,
  type Task,
} from "../api";
import { toChineseSourceKind } from "../markdownUtils";

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
    TODO: "待处理",
    DOING: "处理中",
    DONE: "已完成",
    ERROR: "异常",
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
    NONE: "未触发恢复",
    RETRY_CURRENT_STEP: "重试当前步骤",
    SKIP_FAILED_STEP: "跳过失败步骤继续执行",
    REPLAN_REMAINING_STEPS: "只重建后半段计划",
    REPLAN_FROM_CHECKPOINT: "从检查点重规划",
    REQUIRE_USER_ACTION: "等待用户处理",
    FAIL_FAST: "快速失败",
  };
  return mapping[resolution] ?? resolution;
}

function toChineseStepName(stepName: string) {
  const mapping: Record<string, string> = {
    "Parse Task": "解析任务",
    "Recall Memory": "记忆召回",
    "Read Source Material": "读取资料",
    "Web Research": "联网检索",
    "Create Plan": "生成计划",
    "Draft Deliverable": "撰写回答",
    "Review Output": "结果复核",
  };
  return mapping[stepName] ?? stepName;
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

function roleLabel(role: string) {
  const mapping: Record<string, string> = {
    USER: "用户",
    ASSISTANT: "助手",
    SYSTEM: "系统",
  };
  return mapping[role] ?? role;
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return "暂无时间";
  }
  return new Date(value).toLocaleString("zh-CN");
}

function formatPreviewText(value: unknown) {
  if (value == null) {
    return "暂无";
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function sessionPreviewText(session: Session, detail: SessionDetail | null) {
  if (detail?.session.id === session.id && detail.messages.length) {
    return detail.messages[detail.messages.length - 1]?.content.slice(0, 48) ?? "暂无消息";
  }
  if (session.profile_snapshot?.length) {
    return session.profile_snapshot.join(" · ").slice(0, 48);
  }
  return "点击查看当前会话记录";
}

function pickTypingSlice(fullText: string, currentLength: number) {
  const remaining = fullText.length - currentLength;
  if (remaining <= 0) {
    return currentLength;
  }
  if (remaining <= 6) {
    return fullText.length;
  }
  if (remaining <= 30) {
    return currentLength + 3;
  }
  if (remaining <= 120) {
    return currentLength + 6;
  }
  return currentLength + 10;
}

function renderInline(text: string) {
  const tokens = text.split(/(`[^`]+`|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)/g);
  return tokens.map((token, index) => {
    if (!token) {
      return null;
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return <code key={`${token}-${index}`}>{token.slice(1, -1)}</code>;
    }
    if (token.startsWith("**") && token.endsWith("**")) {
      return <strong key={`${token}-${index}`}>{token.slice(2, -2)}</strong>;
    }
    const linkMatch = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      return (
        <a href={linkMatch[2]} key={`${token}-${index}`} rel="noreferrer" target="_blank">
          {linkMatch[1]}
        </a>
      );
    }
    return <Fragment key={`${token}-${index}`}>{token}</Fragment>;
  });
}

function parseTableRow(line: string) {
  const trimmed = line.trim();
  const normalized = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const withoutTrailing = normalized.endsWith("|") ? normalized.slice(0, -1) : normalized;
  return withoutTrailing.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string) {
  return /^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$/.test(line.trim());
}

function buildCitationSourceMap(task: Task | null) {
  const mapping = new Map<string, Task["citation_sources"][number]>();
  if (!task) {
    return mapping;
  }
  for (const source of task.citation_sources) {
    mapping.set(source.id, source);
  }
  return mapping;
}

function buildCitationFootnoteNumbers(paragraphCitations: Task["paragraph_citations"]) {
  const order = new Map<string, number>();
  let index = 1;
  for (const citation of paragraphCitations) {
    for (const sourceId of citation.source_ids) {
      if (!order.has(sourceId)) {
        order.set(sourceId, index);
        index += 1;
      }
    }
  }
  return order;
}

function buildSourceParagraphMap(paragraphCitations: Task["paragraph_citations"]) {
  const mapping = new Map<string, number[]>();
  for (const citation of paragraphCitations) {
    for (const sourceId of citation.source_ids) {
      const current = mapping.get(sourceId) ?? [];
      current.push(citation.paragraph_index);
      mapping.set(sourceId, current);
    }
  }
  return mapping;
}
function renderInlineCitationAnchors(
  sourceIds: string[],
  footnoteNumbers: Map<string, number>,
  paragraphIndex: number,
) {
  if (!sourceIds.length) {
    return null;
  }
  return (
    <span className="inline-source-anchors">
      {sourceIds.map((sourceId) => {
        const footnoteNumber = footnoteNumbers.get(sourceId);
        if (!footnoteNumber) {
          return null;
        }
        return (
          <a
            className="inline-source-anchor"
            href={`#answer-source-${sourceId}`}
            key={`${paragraphIndex}-${sourceId}`}
            title={`查看来源 ${footnoteNumber}`}
          >
            [{footnoteNumber}]
          </a>
        );
      })}
    </span>
  );
}

function renderMarkdownBlocks(
  markdown: string,
  paragraphCitations: Task["paragraph_citations"],
  footnoteNumbers: Map<string, number>,
) {
  const normalized = markdown.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return [<p key="empty">正在等待内容生成...</p>];
  }

  const lines = normalized.split("\n");
  const elements: ReactNode[] = [];
  let index = 0;
  let key = 0;
  let paragraphCursor = 0;

  while (index < lines.length) {
    const rawLine = lines[index];
    const trimmed = rawLine.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed === "---") {
      elements.push(<hr key={`hr-${key++}`} />);
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      elements.push(
        <pre className="markdown-code-block" key={`code-${key++}`}>
          {language ? <div className="markdown-code-lang">{language}</div> : null}
          <code>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (/^#{1,6}\s+/.test(trimmed)) {
      const level = trimmed.match(/^#+/)?.[0].length ?? 1;
      const content = trimmed.replace(/^#{1,6}\s+/, "");
      const node = level <= 1 ? "h1" : level === 2 ? "h2" : "h3";
      elements.push(
        node === "h1" ? (
          <h1 key={`h1-${key++}`}>{renderInline(content)}</h1>
        ) : node === "h2" ? (
          <h2 key={`h2-${key++}`}>{renderInline(content)}</h2>
        ) : (
          <h3 key={`h3-${key++}`}>{renderInline(content)}</h3>
        ),
      );
      index += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      elements.push(
        <blockquote className="markdown-blockquote" key={`quote-${key++}`}>
          {quoteLines.map((line, lineIndex) => (
            <p key={`quote-line-${lineIndex}`}>{renderInline(line)}</p>
          ))}
        </blockquote>,
      );
      continue;
    }

    if (trimmed.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = parseTableRow(lines[index]);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].trim().includes("|")) {
        rows.push(parseTableRow(lines[index]));
        index += 1;
      }
      elements.push(
        <div className="markdown-table-wrap" key={`table-${key++}`}>
          <table className="markdown-table">
            <thead>
              <tr>
                {headers.map((header, headerIndex) => (
                  <th key={`th-${headerIndex}`}>{renderInline(header)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`tr-${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td key={`td-${rowIndex}-${cellIndex}`}>{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (/^[-*]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
      const items: { ordered: boolean; text: string }[] = [];
      while (index < lines.length) {
        const current = lines[index].trim();
        if (/^[-*]\s+/.test(current)) {
          items.push({ ordered: false, text: current.replace(/^[-*]\s+/, "") });
          index += 1;
          continue;
        }
        if (/^\d+\.\s+/.test(current)) {
          items.push({ ordered: true, text: current.replace(/^\d+\.\s+/, "") });
          index += 1;
          continue;
        }
        break;
      }
      const ListTag = items.every((item) => item.ordered) ? "ol" : "ul";
      elements.push(
        <ListTag key={`list-${key++}`}>
          {items.map((item, itemIndex) => (
            <li key={`${item.text}-${itemIndex}`}>{renderInline(item.text)}</li>
          ))}
        </ListTag>,
      );
      continue;
    }

    const paragraphLines = [trimmed];
    index += 1;
    while (index < lines.length) {
      const current = lines[index].trim();
      if (
        !current ||
        current === "---" ||
        /^#{1,6}\s+/.test(current) ||
        /^[-*]\s+/.test(current) ||
        /^\d+\.\s+/.test(current) ||
        current.startsWith(">") ||
        current.startsWith("```") ||
        (current.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]))
      ) {
        break;
      }
      paragraphLines.push(current);
      index += 1;
    }

    const paragraphCitation = paragraphCitations.find((item) => item.paragraph_index === paragraphCursor);
    const paragraphId = paragraphCitation ? `answer-paragraph-${paragraphCitation.paragraph_index}` : undefined;
    elements.push(
      <p className="answer-paragraph" id={paragraphId} key={`p-${key++}`}>
        {renderInline(paragraphLines.join(" "))}
        {paragraphCitation
          ? renderInlineCitationAnchors(paragraphCitation.source_ids, footnoteNumbers, paragraphCitation.paragraph_index)
          : null}
      </p>,
    );
    paragraphCursor += 1;
  }

  return elements;
}

function ApprovalInline({
  task,
  approval,
  onResolved,
}: {
  task: Task;
  approval: PendingApproval;
  onResolved: (task: Task) => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState(false);

  const decide = async (approved: boolean) => {
    setSubmitting(true);
    try {
      const updated = await confirmTaskApproval(task.id, approval.id, approved);
      await onResolved(updated);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <article className="approval-card">
      <div className="approval-head">
        <div>
          <strong>{approval.operation}</strong>
          <div className="meta">{approval.message}</div>
        </div>
        <span className="approval-badge">等待确认</span>
      </div>
      <div className="meta">{approval.risk_note}</div>
      <div className="actions">
        <button disabled={submitting} onClick={() => void decide(true)}>
          允许继续
        </button>
        <button className="secondary" disabled={submitting} onClick={() => void decide(false)}>
          拒绝操作
        </button>
      </div>
    </article>
  );
}

function ExecutionNodeTimeline({ nodes }: { nodes: ExecutionNode[] }) {
  if (!nodes.length) {
    return <div className="empty-note">当前任务还没有生成可视化执行节点。</div>;
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
              <span>{formatDateTime(node.started_at ?? node.ended_at)}</span>
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

export function ConsolePage() {
  const [goal, setGoal] = useState("请用中文总结这个项目的主要能力，并给出后续优化建议。");
  const [constraints, setConstraints] = useState("输出使用 Markdown\n内容尽量简洁\n优先突出 AI Agent 能力");
  const [sourceText, setSourceText] = useState("请重点说明任务规划、步骤执行、记忆检索和运行配置这几个方面。");
  const [sourcePath, setSourcePath] = useState("");
  const [memoryScope, setMemoryScope] = useState("default");
  const [enableWebSearch, setEnableWebSearch] = useState(true);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [statusText, setStatusText] = useState("准备就绪，可以发起新任务。");
  const [thinkingSummary, setThinkingSummary] = useState("任务开始后，这里会展示完整思考链路与执行进度。");
  const [renderedResult, setRenderedResult] = useState("");
  const [copyText, setCopyText] = useState("复制回答");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [thoughtOpen, setThoughtOpen] = useState(false);
  const [isLaunchingTask, setIsLaunchingTask] = useState(false);

  const resultRef = useRef<HTMLDivElement | null>(null);
  const resultTargetRef = useRef("");
  const copyTimerRef = useRef<number | null>(null);
  const taskStreamRef = useRef<EventSource | null>(null);

  const refreshSessions = async (preferredId?: string | null) => {
    const items = await listSessions();
    setSessions(items);
    const nextId = preferredId ?? selectedSessionId ?? items[0]?.id ?? null;
    setSelectedSessionId(nextId);

    if (!nextId) {
      setSessionDetail(null);
      return;
    }

    const detail = await getSession(nextId);
    setSessionDetail(detail);
    setCurrentTask((active) => {
      if (active?.session_id === detail.session.id) {
        return active;
      }
      return detail.tasks[0] ?? active;
    });
  };

  const refreshTasks = async () => {
    const taskItems = await listTasks();
    setTasks(taskItems);
    setCurrentTask((active) => active ?? taskItems[0] ?? null);
  };
  useEffect(() => {
    void refreshSessions();
    void refreshTasks();
  }, []);

  useEffect(() => {
    const targetText = currentTask?.live_result ?? currentTask?.result ?? "";
    resultTargetRef.current = targetText;

    if (!currentTask || !currentTask.live_result) {
      setRenderedResult(targetText);
      return;
    }

    let cancelled = false;
    let timer = 0;
    const tick = () => {
      if (cancelled) {
        return;
      }
      setRenderedResult((prev) => {
        const latestTarget = resultTargetRef.current;
        if (prev === latestTarget) {
          return prev;
        }
        const nextLength = Math.min(latestTarget.length, pickTypingSlice(latestTarget, prev.length));
        return latestTarget.slice(0, nextLength);
      });
      timer = window.setTimeout(tick, 18);
    };
    timer = window.setTimeout(tick, 18);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [currentTask?.id, currentTask?.live_result, currentTask?.result]);

  useEffect(() => {
    const node = resultRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [renderedResult, currentTask?.progress_updates.length, sessionDetail?.messages.length]);

  useEffect(
    () => () => {
      taskStreamRef.current?.close();
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
    },
    [],
  );

  const ensureSession = async () => {
    if (selectedSessionId) {
      return selectedSessionId;
    }
    const created = await createSession({ title: goal.slice(0, 28) || "新对话" });
    setSelectedSessionId(created.id);
    void refreshSessions(created.id);
    return created.id;
  };

  const refreshAfterTaskUpdate = async (task: Task) => {
    setCurrentTask(task);
    setThoughtOpen(true);
    await refreshTasks();
    if (task.session_id) {
      await refreshSessions(task.session_id);
    }
  };

  const runTask = async () => {
    if (isLaunchingTask) {
      return;
    }

    setIsLaunchingTask(true);
    setThoughtOpen(true);
    taskStreamRef.current?.close();
    taskStreamRef.current = null;

    try {
      setStatusText("正在创建任务并连接实时进度流...");
      setThinkingSummary("系统正在初始化执行链路，稍后会在下方展示查询改写、检索、提示拼接与回答生成过程。");
      setRenderedResult("");

      const sessionId = await ensureSession();
      const task = await launchTask({
        goal,
        constraints: constraints
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
        expected_output: "markdown",
        source_text: sourceText || undefined,
        source_path: sourcePath || undefined,
        memory_scope: memoryScope,
        enable_web_search: enableWebSearch,
        session_id: sessionId,
      });

      setCurrentTask(task);
      setStatusText(`任务已启动，当前状态：${toChineseStatus(task.status)}`);

      const source = streamTask(task.id, {
        onUpdate: (nextTask) => {
          setCurrentTask(nextTask);
          const latestProgress = nextTask.progress_updates[nextTask.progress_updates.length - 1];
          if (latestProgress) {
            setThinkingSummary(
              latestProgress.detail ? `${latestProgress.message}\n${latestProgress.detail}` : latestProgress.message,
            );
          }

          setStatusText(
            nextTask.status === "COMPLETED"
              ? "任务已完成，可以查看最终回答。"
              : nextTask.status === "FAILED"
                ? "任务执行失败，请展开思考过程查看恢复与失败信息。"
                : nextTask.status === "WAITING_APPROVAL"
                  ? "任务正在等待你的确认，确认后会继续执行。"
                  : `任务执行中，当前状态：${toChineseStatus(nextTask.status)}`,
          );

          if (["COMPLETED", "FAILED", "CANCELLED"].includes(nextTask.status)) {
            void refreshTasks();
            if (nextTask.session_id) {
              void refreshSessions(nextTask.session_id);
            }
            taskStreamRef.current?.close();
            taskStreamRef.current = null;
          }
        },
        onError: () => {
          setStatusText("实时进度流中断，已回退为后台刷新。");
          if (sessionId) {
            void refreshSessions(sessionId);
          }
          void refreshTasks();
          taskStreamRef.current = null;
        },
      });

      taskStreamRef.current = source;
      void refreshTasks();
      void refreshSessions(sessionId);
    } catch (error) {
      console.error(error);
      setStatusText("任务启动失败，请稍后重试。");
      setThinkingSummary("当前任务未能正常启动，请检查后端日志或浏览器控制台。");
    } finally {
      setIsLaunchingTask(false);
    }
  };

  const handleNewSession = async () => {
    const created = await createSession({ title: "新对话" });
    setGoal("");
    setRenderedResult("");
    setCurrentTask(null);
    setThoughtOpen(false);
    await refreshSessions(created.id);
  };

  const handleCopyAnswer = async () => {
    const text = renderedResult || currentTask?.result || "";
    if (!text) {
      setCopyText("暂无可复制内容");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopyText("复制成功");
    } catch {
      setCopyText("复制失败");
    }
    if (copyTimerRef.current !== null) {
      window.clearTimeout(copyTimerRef.current);
    }
    copyTimerRef.current = window.setTimeout(() => setCopyText("复制回答"), 1400);
  };

  const activeTask =
    currentTask?.session_id === selectedSessionId ? currentTask : sessionDetail?.tasks[0] ?? currentTask ?? null;
  const pendingApprovals = activeTask?.pending_approvals.filter((item) => item.approved === null) ?? [];
  const isStreaming = Boolean(activeTask && !["COMPLETED", "FAILED", "CANCELLED"].includes(activeTask.status));
  const citationSourceMap = useMemo(() => buildCitationSourceMap(activeTask), [activeTask]);
  const paragraphCitations = activeTask?.paragraph_citations ?? [];
  const footnoteNumbers = useMemo(() => buildCitationFootnoteNumbers(paragraphCitations), [paragraphCitations]);
  const sourceParagraphMap = useMemo(() => buildSourceParagraphMap(paragraphCitations), [paragraphCitations]);
  const renderedMarkdown = useMemo(
    () => renderMarkdownBlocks(renderedResult, paragraphCitations, footnoteNumbers),
    [footnoteNumbers, paragraphCitations, renderedResult],
  );
  const executionNodes = activeTask?.execution_nodes ?? [];

  const latestAssistantTaskId = [...(sessionDetail?.messages ?? [])]
    .reverse()
    .find((message) => message.role === "ASSISTANT" && message.task_id)?.task_id;
  const showLiveAssistantBubble = Boolean(
    activeTask &&
      activeTask.session_id === selectedSessionId &&
      (latestAssistantTaskId !== activeTask.id || isStreaming || pendingApprovals.length),
  );
  return (
    <section className={sidebarCollapsed ? "agent-workspace sidebar-collapsed" : "agent-workspace"}>
      <aside className="agent-sidebar">
        <div className="agent-sidebar-head">
          <div>
            <div className="agent-section-kicker">会话</div>
            <h2>历史对话</h2>
          </div>
          <button className="icon-button secondary" onClick={() => setSidebarCollapsed((prev) => !prev)}>
            {sidebarCollapsed ? "展开" : "收起"}
          </button>
        </div>

        <button className="primary-wide-button" onClick={() => void handleNewSession()}>
          + 新建会话
        </button>

        <div className="session-list">
          {sessions.map((session) => (
            <button
              className={session.id === selectedSessionId ? "session-card active" : "session-card"}
              key={session.id}
              onClick={() => void refreshSessions(session.id)}
            >
              <strong>{session.title}</strong>
              <span>{sessionPreviewText(session, sessionDetail)}</span>
              <small>
                {session.message_count} 条消息 · {formatDateTime(session.updated_at)}
              </small>
            </button>
          ))}
          {!sessions.length ? <div className="empty-note">暂无会话，发送第一条消息后会自动创建。</div> : null}
        </div>
      </aside>

      <main className="agent-main">
        <section className="chat-panel">
          <header className="chat-header">
            <div>
              <div className="agent-section-kicker">当前会话</div>
              <h2>{sessionDetail?.session.title ?? "新对话"}</h2>
              <p className="meta">
                {sessionDetail
                  ? `共 ${sessionDetail.messages.length} 条消息，最近更新时间 ${formatDateTime(sessionDetail.session.updated_at)}`
                  : "选择左侧会话，或直接发送消息开始新对话。"}
              </p>
            </div>
            <div className="toolbar-actions">
              <button className="secondary-button" onClick={() => void refreshSessions(selectedSessionId)}>
                刷新会话
              </button>
              <button className="secondary-button" onClick={() => void refreshTasks()}>
                刷新任务
              </button>
            </div>
          </header>

          <div className="chat-stream" ref={resultRef}>
            {sessionDetail?.messages.map((message) => (
              <article
                className={message.role === "USER" ? "chat-bubble-row user" : "chat-bubble-row assistant"}
                key={message.id}
              >
                <div className="chat-avatar">{message.role === "USER" ? "你" : message.role === "SYSTEM" ? "系" : "AI"}</div>
                <div className="chat-bubble-card">
                  <div className="chat-bubble-head">
                    <strong>{roleLabel(message.role)}</strong>
                    <span>{formatDateTime(message.created_at)}</span>
                  </div>
                  <div className={message.role === "ASSISTANT" ? "markdown-result" : "plain-message"}>
                    {message.role === "ASSISTANT"
                      ? renderMarkdownBlocks(message.content, [], new Map<string, number>())
                      : <p>{message.content}</p>}
                  </div>
                </div>
              </article>
            ))}

            {showLiveAssistantBubble && activeTask ? (
              <article className="chat-bubble-row assistant live-answer-row">
                <div className="chat-avatar">AI</div>
                <div className="chat-bubble-card live-answer-card">
                  <div className="chat-bubble-head">
                    <strong>助手</strong>
                    <span>{toChineseStatus(activeTask.status)}</span>
                  </div>

                  <div className="answer-toolbar">
                    <div className="answer-status-text">{statusText}</div>
                    <div className="toolbar-actions">
                      <button className="secondary-button" onClick={() => void handleCopyAnswer()}>
                        {copyText}
                      </button>
                      {isStreaming ? (
                        <span className="typing-badge">
                          <span className="typing-dot" />
                          正在生成
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <div className={isStreaming ? "markdown-result result-streaming" : "markdown-result"}>
                    {renderedMarkdown}
                    {!renderedResult ? <p className="meta">回答生成后会显示在这里。</p> : null}
                    {isStreaming ? <span className="typing-caret" aria-hidden="true" /> : null}
                  </div>

                  {activeTask.paragraph_citations.length ? (
                    <section className="answer-footnotes">
                      <strong>引用脚注与来源映射</strong>
                      <div className="source-hit-list">
                        {Array.from(footnoteNumbers.entries()).map(([sourceId, footnoteNumber]) => {
                          const source = citationSourceMap.get(sourceId);
                          if (!source) {
                            return null;
                          }
                          const paragraphIndexes = sourceParagraphMap.get(sourceId) ?? [];
                          return (
                            <article className="source-hit-card source-footnote-card" id={`answer-source-${sourceId}`} key={sourceId}>
                              <div className="tool-card-head">
                                <strong>
                                  [{footnoteNumber}] {source.label}
                                </strong>
                                <span className="tool-badge">来源：{toChineseSourceKind(source.kind)}</span>
                              </div>
                              <div className="meta">{source.detail}</div>
                              {paragraphIndexes.length ? (
                                <div className="tag-row">
                                  {paragraphIndexes.map((paragraphIndex) => (
                                    <a className="inline-source-anchor" href={`#answer-paragraph-${paragraphIndex}`} key={`${sourceId}-${paragraphIndex}`}>
                                      段落 {paragraphIndex + 1}
                                    </a>
                                  ))}
                                </div>
                              ) : null}
                              {source.excerpt ? <pre>{source.excerpt}</pre> : null}
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  ) : null}
                  <details className="thought-panel" open={thoughtOpen} onToggle={(event) => setThoughtOpen(event.currentTarget.open)}>
                    <summary>
                      <div>
                        <strong>思考过程</strong>
                        <span>展开查看 Query 改写、向量检索、多路召回、提示拼接、工具调用与恢复链路</span>
                      </div>
                    </summary>

                    <div className="thought-panel-body">
                      <section className="thought-section">
                        <div className="thought-section-head">
                          <strong>阶段摘要</strong>
                          <span>{thinkingSummary}</span>
                        </div>
                        <div className="thought-metrics">
                          <article className="thought-metric-card"><span>当前状态</span><strong>{toChineseStatus(activeTask.status)}</strong></article>
                          <article className="thought-metric-card"><span>失败类型</span><strong>{toChineseFailure(activeTask.checkpoint.last_failure_category)}</strong></article>
                          <article className="thought-metric-card"><span>恢复策略</span><strong>{toChineseResolution(activeTask.checkpoint.last_failure_resolution)}</strong></article>
                          <article className="thought-metric-card"><span>恢复次数</span><strong>{activeTask.checkpoint.recovery_attempt}</strong></article>
                        </div>
                      </section>

                      <section className="thought-section">
                        <div className="thought-section-head">
                          <strong>Agent 执行全流程</strong>
                          <span>这是面向前端可视化的统一执行节点视图，覆盖 Query 改写、检索、Prompt 拼接、步骤执行、工具调用和恢复链路。</span>
                        </div>
                        <ExecutionNodeTimeline nodes={executionNodes} />
                      </section>

                      {pendingApprovals.length ? (
                        <section className="thought-section">
                          <div className="thought-section-head"><strong>待确认操作</strong><span>需要你的授权后系统才会继续执行。</span></div>
                          <div className="stack">
                            {pendingApprovals.map((approval) => (
                              <ApprovalInline approval={approval} key={approval.id} onResolved={async (task) => { await refreshAfterTaskUpdate(task); }} task={activeTask} />
                            ))}
                          </div>
                        </section>
                      ) : null}

                      <section className="thought-section">
                        <div className="thought-section-head"><strong>系统进度</strong><span>按时间顺序展示执行进度、状态切换与中间说明。</span></div>
                        <div className="thought-timeline">
                          {activeTask.progress_updates.map((update) => (
                            <article className="thought-timeline-item" key={update.id}>
                              <div className="thought-timeline-dot" />
                              <div className="thought-timeline-content">
                                <div className="thought-timeline-head"><strong>{update.message}</strong><span>{formatDateTime(update.created_at)}</span></div>
                                <div className="meta">阶段：{update.stage}</div>
                                {update.detail ? <pre>{update.detail}</pre> : null}
                              </div>
                            </article>
                          ))}
                        </div>
                      </section>

                      <section className="thought-section">
                        <div className="thought-section-head"><strong>执行步骤</strong><span>展示规划出来的步骤、当前执行状态与每一步输出。</span></div>
                        <div className="timeline">
                          {activeTask.steps.map((step, index) => {
                            const isRecoveryStart = step.id === activeTask.checkpoint.last_recovery_step_id;
                            return (
                              <article className="timeline-item" key={step.id}>
                                <div className="timeline-rail">
                                  <span className={`timeline-dot timeline-dot-${step.status.toLowerCase()}`} />
                                  {index < activeTask.steps.length - 1 ? <span className="timeline-line" /> : null}
                                </div>
                                <div className={isRecoveryStart ? "timeline-card recovery-step-card" : "timeline-card"}>
                                  <div className="timeline-head"><strong>{toChineseStepName(step.name)}</strong><span className="timeline-status">{toChineseStatus(step.status)}</span></div>
                                  <div className="timeline-desc">{step.description}</div>
                                  {isRecoveryStart ? <div className="meta recovery-step-note">这里是最近一次恢复的起点。</div> : null}
                                  {step.output ? <pre>{step.output}</pre> : <div className="meta">当前步骤尚无输出。</div>}
                                </div>
                              </article>
                            );
                          })}
                          {!activeTask.steps.length ? <div className="empty-note">当前任务还没有生成步骤信息。</div> : null}
                        </div>
                      </section>

                      <section className="thought-grid">
                        <article className="thought-section">
                          <div className="thought-section-head"><strong>检索与记忆</strong><span>覆盖 Query 改写后进入的记忆召回、多路召回和命中来源。</span></div>
                          {activeTask.recalled_memories.length ? (
                            <div className="source-hit-list">
                              {activeTask.recalled_memories.map((memory) => (
                                <article className="source-hit-card" key={memory.id}>
                                  <div className="tool-card-head"><strong>{memory.topic}</strong><span className="tool-badge">{memory.memory_type}</span></div>
                                  <div className="meta">召回分数：{memory.retrieval_score ?? "暂无"} · 命中原因：{memory.retrieval_reason ?? "暂无"}</div>
                                  <div className="meta">召回通道：{memory.retrieval_channels.join(" / ") || "暂无"}</div>
                                  <pre>{memory.summary}</pre>
                                </article>
                              ))}
                            </div>
                          ) : <div className="empty-note">当前任务没有记录到记忆命中。</div>}
                        </article>

                        <article className="thought-section">
                          <div className="thought-section-head"><strong>工具调用</strong><span>展示执行中的工具名称、参数、返回结果和异常信息。</span></div>
                          {activeTask.tool_invocations.length ? (
                            <div className="source-hit-list">
                              {activeTask.tool_invocations.map((tool) => (
                                <article className="source-hit-card" key={tool.id}>
                                  <div className="tool-card-head"><strong>{tool.tool_name}</strong><span className="tool-badge">{tool.status}</span></div>
                                  <div className="meta">尝试次数 {tool.attempt_count} · 失败类型 {toChineseFailure(tool.failure_category)}</div>
                                  <pre>{formatPreviewText(tool.input_payload)}</pre>
                                  {tool.output_preview ? <pre>{tool.output_preview}</pre> : null}
                                  {tool.error ? <pre>{tool.error}</pre> : null}
                                </article>
                              ))}
                            </div>
                          ) : <div className="empty-note">当前任务还没有记录工具调用。</div>}
                        </article>
                      </section>

                      <section className="thought-grid">
                        <article className="thought-section">
                          <div className="thought-section-head"><strong>上下文分层与提示拼接</strong><span>展示系统提示、会话摘要、压缩上下文、工作记忆与拼接说明。</span></div>
                          <div className="stack">
                            <article className="thought-info-card"><strong>系统指令</strong><pre>{activeTask.context_layers.system_instructions || "暂无"}</pre></article>
                            <article className="thought-info-card"><strong>会话摘要</strong><pre>{activeTask.context_layers.session_summary || "暂无"}</pre></article>
                            <article className="thought-info-card"><strong>压缩后的最近消息</strong><pre>{activeTask.context_layers.condensed_recent_messages.join("\n") || "暂无"}</pre></article>
                            <article className="thought-info-card"><strong>工作记忆 / 构建说明</strong><pre>{[...activeTask.context_layers.working_memory, ...activeTask.context_layers.build_notes].join("\n") || "暂无"}</pre></article>
                          </div>
                        </article>

                        <article className="thought-section">
                          <div className="thought-section-head"><strong>重规划与恢复链路</strong><span>展示失败分类、从哪一步恢复，以及是否触发重新规划。</span></div>
                          {activeTask.replan_history.length ? (
                            <div className="source-hit-list">
                              {activeTask.replan_history.map((event) => (
                                <article className="source-hit-card" key={event.id}>
                                  <div className="tool-card-head"><strong>{event.summary}</strong><span className="tool-badge">{toChineseFailure(event.failure_category)}</span></div>
                                  <div className="meta">恢复起点：{event.resume_from_step_name ?? "暂无"} · 策略：{event.recovery_strategy}</div>
                                  {event.detail ? <pre>{event.detail}</pre> : null}
                                </article>
                              ))}
                            </div>
                          ) : <div className="empty-note">本次任务未触发重规划或恢复。</div>}
                        </article>
                      </section>
                    </div>
                  </details>
                </div>
              </article>
            ) : null}

            {!sessionDetail?.messages.length && !showLiveAssistantBubble ? (
              <div className="chat-empty-state">
                <strong>开始一段新的 Agent 对话</strong>
                <p>输入问题后，右侧会显示当前对话、最终回答，以及可折叠的完整思考过程。</p>
              </div>
            ) : null}
          </div>

          <footer className="composer-card">
            <div className="composer-header">
              <div><strong>向 Agent 提问</strong><div className="meta">最终默认只展示 LLM 结果，思考过程折叠在回答下方。</div></div>
              <button className="secondary-button" onClick={() => setAdvancedOpen((prev) => !prev)}>{advancedOpen ? "收起高级选项" : "展开高级选项"}</button>
            </div>

            <label className="composer-label">
              输入问题
              <textarea className="composer-textarea" onChange={(event) => setGoal(event.target.value)} placeholder="例如：帮我分析这个项目接下来三周的开发优先级" value={goal} />
            </label>

            {advancedOpen ? (
              <div className="composer-advanced-grid">
                <label>输出约束<textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} /></label>
                <label>参考文本<textarea value={sourceText} onChange={(event) => setSourceText(event.target.value)} /></label>
                <label>本地文件路径<input onChange={(event) => setSourcePath(event.target.value)} placeholder="可选，用于权限确认或读取本地资料" value={sourcePath} /></label>
                <label>记忆作用域<input onChange={(event) => setMemoryScope(event.target.value)} value={memoryScope} /></label>
                <label className="checkbox"><input checked={enableWebSearch} onChange={(event) => setEnableWebSearch(event.target.checked)} type="checkbox" />启用联网检索</label>
              </div>
            ) : null}

            <div className="composer-actions">
              <button disabled={isLaunchingTask || !goal.trim()} onClick={() => void runTask()}>{isLaunchingTask ? "正在发送..." : "发送问题"}</button>
              <span className="meta">{statusText}</span>
            </div>
          </footer>
        </section>
      </main>
    </section>
  );
}

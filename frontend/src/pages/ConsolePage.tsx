import { Fragment, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import {
  commitIngestion,
  confirmTaskApproval,
  createSession,
  getSession,
  launchTask,
  listSessions,
  listTasks,
  previewIngestion,
  streamTask,
  type ChunkPreview,
  type ExecutionNode,
  type IngestionCommitResponse,
  type IngestionStrategy,
  type IngestionPreviewResponse,
  type PendingApproval,
  type Session,
  type SessionDetail,
  type Task,
} from "../api";
import type { DragEvent } from "react";

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

function toChineseToolCallStatus(status: string) {
  const mapping: Record<string, string> = {
    SUCCESS: "成功",
    ERROR: "失败",
  };
  return mapping[status] ?? toChineseStatus(status);
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

function toChineseIngestionStrategy(strategy: IngestionStrategy) {
  const mapping: Record<IngestionStrategy, string> = {
    recursive: "递归切分",
    parent_child: "父子文档",
    semantic: "语义分段",
  };
  return mapping[strategy] ?? strategy;
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

function sessionDisplayTitle(session: Session) {
  const normalized = session.title.replace(/\s+/g, " ").trim();
  return normalized || "新对话";
}

function sessionHistoryMeta(session: Session) {
  return `${session.message_count} 条消息 · ${formatDateTime(session.created_at)}`;
}

function isTaskInStreamingState(status?: string | null) {
  return Boolean(status && !["COMPLETED", "FAILED", "CANCELLED"].includes(status));
}

function sanitizeVisibleAssistantMarkdown(markdown: string) {
  let normalized = markdown.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return "";
  }

  const answerBlockMatch = normalized.match(
    /(?:^|\n)(?:##?\s*)?(?:回答内容|回答正文|Answer Content|Deliverable)\s*\n+([\s\S]*?)(?=\n(?:##?\s*)?(?:结果说明|工具调用|来源文件|Result Notes|Tool Invocations?|Source)\b|$)/i,
  );
  if (answerBlockMatch?.[1]) {
    normalized = answerBlockMatch[1].trim();
  }

  const fallbackAnswerMatch = normalized.match(
    /##\s*(回答内容|Answer Content)\s*\n+([\s\S]*?)(?=\n##\s*(结果说明|工具调用|来源文件|Result Notes|Tool Invocations?|Source)\b|$)/i,
  );
  if (fallbackAnswerMatch?.[2]) {
    normalized = fallbackAnswerMatch[2].trim();
  }

  normalized = normalized.replace(/^\s*#\s*(AI\s*助手执行结果|AI\s*Agent\s*执行结果|Agent\s*执行结果)\s*\n+/i, "");
  normalized = normalized.replace(/^\s*(AI\s*助手执行结果|AI\s*Agent\s*执行结果|Agent\s*执行结果)\s*\n+/i, "");
  normalized = normalized.replace(
    /^\s*##\s*(任务目标|Goal)\s*\n+[\s\S]*?(?=\n##\s*(回答正文|回答内容|Deliverable|Answer Content)\b|$)/i,
    "",
  );
  normalized = normalized.replace(
    /^\s*(任务目标|Goal)\s*\n+[\s\S]*?(?=\n(?:回答正文|回答内容|Deliverable|Answer Content)\b|$)/i,
    "",
  );
  normalized = normalized.replace(
    /^-\s*([a-zA-Z_]+)\s+\((SUCCESS|ERROR), attempt (\d+), category ([A-Z_]+)\):\s*(.+)$/gm,
    "",
  );
  normalized = normalized.replace(/^- No tools were called\.\s*$/gm, "");
  normalized = normalized.replace(/^- 本轮对话未调用外部工具。\s*$/gm, "");

  normalized = normalized.replace(/^\s*##\s*(回答正文|Deliverable)\s*\n+/i, "");
  normalized = normalized.replace(/^\s*(回答正文|回答内容|Deliverable|Answer Content)\s*\n+/i, "");
  normalized = normalized.replace(/\n##\s*(结果说明|工具调用|Tool Invocations?|来源文件|Source|Result Notes)\b[\s\S]*$/i, "");
  normalized = normalized.replace(/\n(?:结果说明|工具调用|Tool Invocations?|来源文件|Source|Result Notes)\b[\s\S]*$/i, "");
  normalized = normalized.replace(/^\s*本轮对话(?:未调用外部工具|调用了.*)$/gim, "");
  normalized = normalized.replace(/^\s*调用了“.*$/gim, "");
  normalized = normalized.replace(/\n{3,}/g, "\n\n");
  return normalized.trim();
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
  const [goal, setGoal] = useState("");
  const [constraints, setConstraints] = useState("");
  const [sourceText, setSourceText] = useState("");
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
  const [contextCollapsed, setContextCollapsed] = useState(false);
  const [chatExpanded, setChatExpanded] = useState(false);
  const [activeContextCard, setActiveContextCard] = useState("会话摘要");
  const [ingestionTitle, setIngestionTitle] = useState("");
  const [ingestionText, setIngestionText] = useState("");
  const [ingestionScope, setIngestionScope] = useState("default");
  const [ingestionStrategy, setIngestionStrategy] = useState<IngestionStrategy>("recursive");
  const [ingestionChunkChars, setIngestionChunkChars] = useState(420);
  const [ingestionOverlapChars, setIngestionOverlapChars] = useState(48);
  const [ingestionPreview, setIngestionPreview] = useState<IngestionPreviewResponse | null>(null);
  const [ingestionCommit, setIngestionCommit] = useState<IngestionCommitResponse | null>(null);
  const [ingestionBusy, setIngestionBusy] = useState(false);
  const [ingestionMessage, setIngestionMessage] = useState("输入长文本后，可先预览切块与向量化结果，再决定是否入库。");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [thoughtOpen, setThoughtOpen] = useState(false);
  const [isLaunchingTask, setIsLaunchingTask] = useState(false);
  const [typingTaskId, setTypingTaskId] = useState<string | null>(null);
  const [isComposerDragActive, setIsComposerDragActive] = useState(false);

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

    const shouldAnimate =
      Boolean(currentTask?.live_result) &&
      isTaskInStreamingState(currentTask?.status) &&
      currentTask?.id === typingTaskId;

    if (!shouldAnimate) {
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
  }, [currentTask?.id, currentTask?.live_result, currentTask?.result, currentTask?.status, typingTaskId]);

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
    await refreshTasks();
    if (task.session_id) {
      await refreshSessions(task.session_id);
    }
  };

  const runTask = async () => {
    if (isLaunchingTask) {
      return;
    }

    const submittedGoal = goal;
    setIsLaunchingTask(true);
    setThoughtOpen(false);
    taskStreamRef.current?.close();
    taskStreamRef.current = null;

    try {
      setStatusText("正在创建任务并连接实时进度流...");
      setThinkingSummary("系统正在初始化执行链路，稍后会在下方展示查询改写、检索、提示拼接与回答生成过程。");
      setRenderedResult("");
      setGoal("");

      const sessionId = await ensureSession();
      const task = await launchTask({
        goal: submittedGoal,
        constraints: constraints
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
        expected_output: "markdown",
        source_text: sourceText || undefined,
        enable_web_search: enableWebSearch,
        session_id: sessionId,
      });

      setCurrentTask(task);
      setTypingTaskId(task.id);
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
            setTypingTaskId(null);
            void refreshTasks();
            if (nextTask.session_id) {
              void refreshSessions(nextTask.session_id);
            }
            taskStreamRef.current?.close();
            taskStreamRef.current = null;
          }
        },
        onError: () => {
          setTypingTaskId(null);
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
      setGoal((current) => current || submittedGoal);
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
    const text = sanitizeVisibleAssistantMarkdown(renderedResult || currentTask?.result || "");
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

  const handleComposerFileDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsComposerDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (!file) {
      return;
    }

    try {
      const text = await file.text();
      const nextSourceText = [`[文件] ${file.name}`, text].filter(Boolean).join("\n\n");
      setSourceText((previous) => (previous.trim() ? `${previous}\n\n${nextSourceText}` : nextSourceText));
      setAdvancedOpen(true);
      setStatusText(`已载入文件：${file.name}，内容已写入“参考文本”。`);
    } catch (error) {
      console.error(error);
      setStatusText(`文件读取失败：${file.name}`);
    }
  };

  const buildIngestionPayload = () => ({
    title: ingestionTitle.trim() || undefined,
    text: ingestionText,
    scope: ingestionScope.trim() || "default",
    memory_type: "document_note",
    chunk_strategy: ingestionStrategy,
    max_chunk_chars: ingestionChunkChars,
    overlap_chars: ingestionOverlapChars,
    tags: ["manual_vectorization"],
  });

  const handlePreviewIngestion = async () => {
    if (!ingestionText.trim() || ingestionBusy) {
      return;
    }
    setIngestionBusy(true);
    setIngestionCommit(null);
    setIngestionMessage("正在执行切块与向量化预览...");
    try {
      const preview = await previewIngestion(buildIngestionPayload());
      setIngestionPreview(preview);
      setIngestionMessage(`已生成 ${preview.total_chunks} 个分块，可继续确认入库。`);
    } catch (error) {
      console.error(error);
      setIngestionMessage("向量化预览失败，请检查输入内容或后端服务。");
    } finally {
      setIngestionBusy(false);
    }
  };

  const handleCommitIngestion = async () => {
    if (!ingestionText.trim() || ingestionBusy) {
      return;
    }
    setIngestionBusy(true);
    setIngestionMessage("正在写入记忆库和向量索引...");
    try {
      const committed = await commitIngestion(buildIngestionPayload());
      setIngestionCommit(committed);
      setIngestionMessage(`已入库 ${committed.stored_count} 条记录。`);
      await refreshSessions(selectedSessionId);
    } catch (error) {
      console.error(error);
      setIngestionMessage("入库失败，请稍后重试。");
    } finally {
      setIngestionBusy(false);
    }
  };

  const activeTask =
    currentTask?.session_id === selectedSessionId ? currentTask : sessionDetail?.tasks[0] ?? currentTask ?? null;
  const pendingApprovals = activeTask?.pending_approvals.filter((item) => item.approved === null) ?? [];
  const isStreaming = isTaskInStreamingState(activeTask?.status);
  const isTypingLive = Boolean(activeTask && activeTask.id === typingTaskId && isStreaming);
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
  const visibleAnswerText = sanitizeVisibleAssistantMarkdown(
    activeTask && currentTask?.id === activeTask.id ? renderedResult || activeTask.result || "" : activeTask?.result || "",
  );
  const contextCards = [
    {
      title: "会话摘要",
      icon: "◎",
      hint: "查看当前会话摘要与消息数量",
      body: sessionDetail?.session.context_summary || "当前会话还没有生成摘要，将基于消息与任务实时整理。",
      meta: sessionDetail ? `${sessionDetail.messages.length} 条消息` : "等待会话创建",
    },
    {
      title: "用户画像",
      icon: "◫",
      hint: "查看当前任务命中的用户画像事实",
      body: activeTask?.profile_hits.length
        ? activeTask.profile_hits.map((item) => `${item.label}：${item.value}`).slice(0, 3).join("；")
        : "当前任务还没有命中明确的用户画像事实。",
      meta: `画像命中 ${activeTask?.profile_hits.length ?? 0} 条`,
    },
    {
      title: "记忆召回",
      icon: "◌",
      hint: "查看记忆命中结果与召回摘要",
      body: activeTask?.recalled_memories.length
        ? activeTask.recalled_memories
            .map((item) => `${item.topic}（${item.retrieval_reason ?? "命中"}）`)
            .slice(0, 3)
            .join("；")
        : "当前任务还没有记录到记忆命中。",
      meta: `记忆命中 ${activeTask?.recalled_memories.length ?? 0} 条`,
    },
    {
      title: "执行态势",
      icon: "⌘",
      hint: "查看任务状态、失败类型与恢复策略",
      body: activeTask
        ? `当前状态 ${toChineseStatus(activeTask.status)}，失败类型 ${toChineseFailure(activeTask.checkpoint.last_failure_category)}，恢复策略 ${toChineseResolution(activeTask.checkpoint.last_failure_resolution)}。`
        : "发送问题后，这里会显示本次任务的执行状态、恢复信息和上下文摘要。",
      meta: activeTask ? `执行节点 ${executionNodes.length} 个` : "暂无执行任务",
    },
    {
      title: "手动向量化",
      icon: "✦",
      hint: "手动输入长文本，预览切块与向量化结果后再决定是否入库",
      body: ingestionMessage,
      meta: ingestionPreview ? `已预览 ${ingestionPreview.total_chunks} 个分块` : "尚未开始",
    },
  ];

  const selectedContextCard = contextCards.find((card) => card.title === activeContextCard) ?? contextCards[0];
  const isManualVectorizationSelected = selectedContextCard.title === "手动向量化";

  const handleContextCardSelect = (title: string) => {
    setActiveContextCard(title);
    if (contextCollapsed) {
      setContextCollapsed(false);
    }
  };

  const shellClassName = [
    "gemini-console-shell",
    contextCollapsed ? "context-collapsed" : "",
    chatExpanded ? "chat-expanded" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={shellClassName}>
      <aside className="gemini-history-sidebar">
        <div className="gemini-sidebar-head">
          <button className="gemini-icon-button" onClick={() => void refreshSessions(selectedSessionId)} type="button">
            ⟳
          </button>
        </div>

        <button className="gemini-new-chat-button" onClick={() => void handleNewSession()} type="button">
          <span>✎</span>
          <strong>新对话</strong>
        </button>

        <div className="gemini-sidebar-section">
          <div className="gemini-sidebar-label">最近会话</div>
          <div className="gemini-history-list">
            {sessions.map((session) => (
              <button
                className={session.id === selectedSessionId ? "gemini-history-item active" : "gemini-history-item"}
                key={session.id}
                onClick={() => void refreshSessions(session.id)}
                type="button"
              >
                <strong title={sessionDisplayTitle(session)}>{sessionDisplayTitle(session)}</strong>
                <span>{sessionHistoryMeta(session)}</span>
              </button>
            ))}
            {!sessions.length ? <div className="empty-note">暂无会话，发送第一条消息后会自动创建。</div> : null}
          </div>
        </div>

      </aside>

      <main className={chatExpanded ? "gemini-chat-stage expanded" : "gemini-chat-stage"}>
        <header className="gemini-chat-header">
          <div>
            <h1>{sessionDetail?.session.title ?? "新对话"}</h1>
            <p>
              {sessionDetail
                ? `共 ${sessionDetail.messages.length} 条消息，最近更新时间 ${formatDateTime(sessionDetail.session.updated_at)}`
                : "输入第一个问题后会自动创建会话，并在左侧生成历史记录。"}
            </p>
          </div>
          <div className="gemini-chat-header-actions">
            <button
              className="gemini-icon-button"
              onClick={() => setChatExpanded((prev) => !prev)}
              title={chatExpanded ? "还原聊天窗口宽度" : "放大聊天窗口"}
              type="button"
            >
              {chatExpanded ? "▣" : "□"}
            </button>
            <div className="gemini-user-badge">M</div>
          </div>
        </header>

        <section className="gemini-chat-scroll" ref={resultRef}>
          <div className="gemini-answer-block">
            {sessionDetail?.messages.map((message) => (
              <article className={message.role === "USER" ? "gemini-message user" : "gemini-message assistant"} key={message.id}>
                <div className="gemini-message-meta">
                  <span>{roleLabel(message.role)}</span>
                  <time>{formatDateTime(message.created_at)}</time>
                </div>
                {message.role === "ASSISTANT" ? (
                  <div className="gemini-answer-markdown">
                    {renderMarkdownBlocks(sanitizeVisibleAssistantMarkdown(message.content), [], new Map<string, number>())}
                  </div>
                ) : (
                  <p>{message.content}</p>
                )}
              </article>
            ))}

            {showLiveAssistantBubble && activeTask ? (
              <article className="gemini-message assistant">
                <div className="gemini-message-meta">
                  <span>Orion</span>
                  <time>{toChineseStatus(activeTask.status)}</time>
                </div>

                <details className="gemini-thinking-inline" open={thoughtOpen} onToggle={(event) => setThoughtOpen(event.currentTarget.open)}>
                  <summary>
                    <div className="gemini-thinking-summary-left">
                      <span className="gemini-thinking-star">✦</span>
                      <div>
                        <strong>{thoughtOpen ? "收起思考过程" : "展开思考过程"}</strong>
                        <p>{thinkingSummary}</p>
                      </div>
                    </div>
                    <span className="gemini-thinking-state">
                      {thoughtOpen ? "已展开" : isStreaming ? "回答生成中" : "点击查看"}
                    </span>
                  </summary>

                  <div className="gemini-thinking-body">
                    <article className="gemini-thinking-item">
                      <div className="gemini-thinking-dot active" />
                      <div className="gemini-thinking-card">
                        <div className="gemini-thinking-card-head">
                          <strong>阶段摘要</strong>
                          <span>{toChineseStatus(activeTask.status)}</span>
                        </div>
                        <p>{statusText}</p>
                      </div>
                    </article>
                  </div>

                  <div className="thought-panel-body">
                    <section className="thought-section">
                      <div className="thought-section-head">
                        <strong>任务态势</strong>
                        <span>这里汇总当前状态、失败分类、恢复策略与恢复次数。</span>
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
                        <span>覆盖 Query 改写、检索、Prompt 拼接、执行步骤、工具调用与恢复链路。</span>
                      </div>
                      <ExecutionNodeTimeline nodes={executionNodes} />
                    </section>

                    {pendingApprovals.length ? (
                      <section className="thought-section">
                        <div className="thought-section-head"><strong>待确认操作</strong><span>需要你的授权后系统才会继续执行。</span></div>
                        <div className="stack">
                          {pendingApprovals.map((approval) => (
                            <ApprovalInline
                              approval={approval}
                              key={approval.id}
                              onResolved={async (task) => {
                                await refreshAfterTaskUpdate(task);
                              }}
                              task={activeTask}
                            />
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
                        <div className="thought-section-head"><strong>检索与记忆</strong><span>展示命中的记忆、召回分数、命中原因和召回通道。</span></div>
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
                        <div className="thought-section-head"><strong>工具调用</strong><span>展示工具名称、输入参数、输出摘要和异常信息。</span></div>
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
                        <div className="thought-section-head"><strong>上下文分层</strong><span>展示系统指令、会话摘要、压缩上下文与工作记忆。</span></div>
                        <div className="stack">
                          <article className="thought-info-card"><strong>系统指令</strong><pre>{activeTask.context_layers.system_instructions || "暂无"}</pre></article>
                          <article className="thought-info-card"><strong>会话摘要</strong><pre>{activeTask.context_layers.session_summary || "暂无"}</pre></article>
                          <article className="thought-info-card"><strong>压缩后的最近消息</strong><pre>{activeTask.context_layers.condensed_recent_messages.join("\n") || "暂无"}</pre></article>
                          <article className="thought-info-card"><strong>工作记忆 / 构建说明</strong><pre>{[...activeTask.context_layers.working_memory, ...activeTask.context_layers.build_notes].join("\n") || "暂无"}</pre></article>
                        </div>
                      </article>

                      <article className="thought-section">
                        <div className="thought-section-head"><strong>重规划与恢复链路</strong><span>展示失败分类、恢复起点以及重规划历史。</span></div>
                        {activeTask.replan_history.length ? (
                          <div className="source-hit-list">
                            {activeTask.replan_history.map((event) => (
                              <article className="source-hit-card" key={event.id}>
                                <div className="tool-card-head"><strong>{event.summary}</strong><span className="tool-badge">{toChineseFailure(event.failure_category)}</span></div>
                                <div className="meta">恢复起点：{event.resume_from_step_name ?? "暂无"} · 策略：{event.recovery_strategy}</div>
                                <div className="meta">恢复次数：{event.recovery_attempts}</div>
                                {event.detail ? <pre>{event.detail}</pre> : null}
                              </article>
                            ))}
                          </div>
                        ) : <div className="empty-note">本次任务未触发重规划或恢复。</div>}
                      </article>
                    </section>
                  </div>
                </details>

                <div className={isTypingLive ? "gemini-answer-markdown result-streaming" : "gemini-answer-markdown"}>
                  {visibleAnswerText ? renderMarkdownBlocks(visibleAnswerText, paragraphCitations, footnoteNumbers) : <p className="meta">回答生成后会显示在这里。</p>}
                  {isTypingLive ? <span className="typing-caret" aria-hidden="true" /> : null}
                </div>

                <div className="gemini-answer-actions">
                  <button className="gemini-text-button compact" onClick={() => void handleCopyAnswer()} type="button">
                    {copyText}
                  </button>
                </div>
              </article>
            ) : null}

            {!sessionDetail?.messages.length && !showLiveAssistantBubble ? (
              <div className="gemini-empty-state">
                <strong>开始一段新的 Agent 对话</strong>
                <p>输入问题后，回答区会输出最终正文；思考过程、执行链路与来源锚点会折叠在回答下方。</p>
              </div>
            ) : null}
          </div>
        </section>

        <footer className="gemini-composer-shell">
          <div
            className={isComposerDragActive ? "gemini-composer-box drag-active" : "gemini-composer-box"}
            onDragEnter={(event) => {
              event.preventDefault();
              setIsComposerDragActive(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
                return;
              }
              setIsComposerDragActive(false);
            }}
            onDragOver={(event) => {
              event.preventDefault();
              if (!isComposerDragActive) {
                setIsComposerDragActive(true);
              }
            }}
            onDrop={(event) => void handleComposerFileDrop(event)}
          >
            <textarea
              className="composer-textarea"
              onChange={(event) => setGoal(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== "Enter" || event.shiftKey) {
                  return;
                }
                event.preventDefault();
                if (!goal.trim() || isLaunchingTask) {
                  return;
                }
                void runTask();
              }}
              placeholder="输入问题，系统会在回答下方用可折叠卡片展示完整思考与执行过程。"
              value={goal}
            />
            <div className="gemini-composer-toolbar">
              <details className="detail-toggle composer-detail-toggle" onToggle={(event) => setAdvancedOpen(event.currentTarget.open)} open={advancedOpen}>
                <summary>高级选项</summary>
                <div className="detail-body">
                  <div className="composer-advanced-grid">
                    <label>输出约束<textarea onChange={(event) => setConstraints(event.target.value)} value={constraints} /></label>
                    <label>参考文本<textarea onChange={(event) => setSourceText(event.target.value)} value={sourceText} /></label>
                    <label className="checkbox"><input checked={enableWebSearch} onChange={(event) => setEnableWebSearch(event.target.checked)} type="checkbox" />启用联网检索</label>
                  </div>
                </div>
              </details>
              <div className="gemini-composer-right">
                <button className="gemini-send-button" disabled={isLaunchingTask || !goal.trim()} onClick={() => void runTask()} type="button">
                  {isLaunchingTask ? "…" : "⬆"}
                </button>
              </div>
            </div>
          </div>
        </footer>
      </main>

      <aside className={contextCollapsed ? "gemini-context-rail collapsed" : "gemini-context-rail"}>
        <div className="gemini-context-toolbar">
          {!contextCollapsed ? (
            <div className="gemini-rail-icons">
              {contextCards.map((card) => (
                <button
                  aria-label={card.title}
                  className={activeContextCard === card.title ? "gemini-rail-button active" : "gemini-rail-button"}
                  key={card.title}
                  onClick={() => handleContextCardSelect(card.title)}
                  title={card.hint}
                  type="button"
                >
                  {card.icon}
                </button>
              ))}
            </div>
          ) : null}
          <button
            aria-label={contextCollapsed ? "展开右侧上下文栏" : "收起右侧上下文栏"}
            className="gemini-icon-button"
            onClick={() => setContextCollapsed((prev) => !prev)}
            title={contextCollapsed ? "展开右侧上下文栏" : "收起右侧上下文栏"}
            type="button"
          >
            {contextCollapsed ? "◀" : "▶"}
          </button>
        </div>

        {!contextCollapsed ? (
          <section className="gemini-context-panel">
            <header className="gemini-context-head">
              <div>
                <h2>{selectedContextCard.title}</h2>
              </div>
              <button
                className="gemini-icon-button"
                onClick={() => {
                  void refreshTasks();
                  void refreshSessions(selectedSessionId);
                }}
                title="刷新右侧上下文信息"
                type="button"
              >
                ⟳
              </button>
            </header>

            <div className="gemini-context-list">
              {isManualVectorizationSelected ? (
                <article className="gemini-context-card active vectorization-panel">
                  <label className="vectorization-field">
                    <span>文档标题</span>
                    <input
                      onChange={(event) => setIngestionTitle(event.target.value)}
                      placeholder="可选，默认提取首行"
                      type="text"
                      value={ingestionTitle}
                    />
                  </label>

                  <label className="vectorization-field">
                    <span>待向量化文本</span>
                    <textarea
                      className="vectorization-textarea"
                      onChange={(event) => setIngestionText(event.target.value)}
                      placeholder="粘贴长文本，系统会按所选策略切块并展示向量化预览。"
                      value={ingestionText}
                    />
                  </label>

                  <div className="vectorization-grid">
                    <label className="vectorization-field">
                      <span>切块策略</span>
                      <select onChange={(event) => setIngestionStrategy(event.target.value as IngestionStrategy)} value={ingestionStrategy}>
                        <option value="recursive">递归切分</option>
                        <option value="parent_child">父子文档</option>
                        <option value="semantic">语义分段</option>
                      </select>
                    </label>

                    <label className="vectorization-field">
                      <span>作用域</span>
                      <input onChange={(event) => setIngestionScope(event.target.value)} type="text" value={ingestionScope} />
                    </label>

                    <label className="vectorization-field">
                      <span>分块长度</span>
                      <input
                        min={8}
                        onChange={(event) => setIngestionChunkChars(Number(event.target.value) || 8)}
                        type="number"
                        value={ingestionChunkChars}
                      />
                    </label>

                    <label className="vectorization-field">
                      <span>重叠长度</span>
                      <input
                        min={0}
                        onChange={(event) => setIngestionOverlapChars(Number(event.target.value) || 0)}
                        type="number"
                        value={ingestionOverlapChars}
                      />
                    </label>
                  </div>

                  <div className="vectorization-actions">
                    <button className="gemini-text-button compact" disabled={ingestionBusy || !ingestionText.trim()} onClick={() => void handlePreviewIngestion()} type="button">
                      {ingestionBusy ? "处理中..." : "开始向量化"}
                    </button>
                    <button
                      className="gemini-text-button compact"
                      disabled={ingestionBusy || !ingestionText.trim() || !ingestionPreview}
                      onClick={() => void handleCommitIngestion()}
                      type="button"
                    >
                      确认入库
                    </button>
                  </div>

                  <div className="meta">{ingestionMessage}</div>

                  {ingestionPreview ? (
                    <div className="vectorization-preview-list">
                      <article className="vectorization-preview-summary">
                        <strong>{ingestionPreview.title}</strong>
                        <span>
                          {toChineseIngestionStrategy(ingestionPreview.strategy)} · {ingestionPreview.total_chunks} 个分块 · 父文档 {ingestionPreview.parent_documents_count} 个
                        </span>
                      </article>
                      {ingestionPreview.chunks.map((chunk: ChunkPreview) => (
                        <article className="vectorization-preview-card" key={chunk.chunk_id}>
                          <div className="tool-card-head">
                            <strong>分块 {chunk.chunk_index + 1}</strong>
                            <span className="tool-badge">{chunk.embedding_dimensions} 维</span>
                          </div>
                          {chunk.parent_id ? <div className="meta">父文档：{chunk.parent_id}</div> : null}
                          <div className="meta">字符数：{chunk.char_count}</div>
                          <pre>{chunk.text}</pre>
                          <div className="meta">向量预览：[{chunk.embedding_preview.join(", ")}]</div>
                        </article>
                      ))}
                    </div>
                  ) : null}

                  {ingestionCommit ? (
                    <article className="vectorization-preview-summary">
                      <strong>入库完成</strong>
                      <span>
                        已写入 {ingestionCommit.stored_count} 条记录，分块 {ingestionCommit.chunk_count} 个，作用域 {ingestionCommit.scope}
                      </span>
                    </article>
                  ) : null}
                </article>
              ) : (
                <article className="gemini-context-card active">
                  <p>{selectedContextCard.body}</p>
                  <span>{selectedContextCard.meta}</span>
                </article>
              )}
            </div>
          </section>
        ) : null}
      </aside>
    </section>
  );
}

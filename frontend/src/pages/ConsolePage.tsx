import { Fragment, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { launchTask, listTasks, searchMemories, streamTask, type MemoryRecord, type Task } from "../api";

function toChineseStatus(status: string) {
  const mapping: Record<string, string> = {
    CREATED: "已创建",
    PARSED: "已解析",
    PLANNED: "已规划",
    RUNNING: "执行中",
    WAITING_TOOL: "等待工具",
    REFLECTING: "复核中",
    COMPLETED: "已完成",
    FAILED: "失败",
    CANCELLED: "已取消",
    TODO: "待处理",
    DOING: "处理中",
    DONE: "已完成",
    ERROR: "错误",
    SKIPPED: "已跳过",
    RETRYING: "重试中",
  };
  return mapping[status] ?? status;
}

function toChineseStepName(stepName: string) {
  const mapping: Record<string, string> = {
    "Parse Task": "解析任务",
    "Recall Memory": "召回记忆",
    "Read Source Material": "读取参考材料",
    "Web Research": "联网检索",
    "Create Plan": "生成计划",
    "Draft Deliverable": "撰写结果",
    "Review Output": "结果复核",
  };
  return mapping[stepName] ?? stepName;
}

function pickTypingSlice(fullText: string, currentLength: number) {
  const remaining = fullText.length - currentLength;
  if (remaining <= 0) {
    return currentLength;
  }
  if (remaining <= 4) {
    return fullText.length;
  }
  if (remaining <= 20) {
    return currentLength + 2;
  }
  if (remaining <= 80) {
    return currentLength + 4;
  }
  return currentLength + 8;
}

function renderInline(text: string) {
  const segments = text.split(/(`[^`]+`)/g);
  return segments.map((segment, index) => {
    if (segment.startsWith("`") && segment.endsWith("`")) {
      return <code key={`${segment}-${index}`}>{segment.slice(1, -1)}</code>;
    }
    return <Fragment key={`${segment}-${index}`}>{segment}</Fragment>;
  });
}

function renderMarkdownBlocks(markdown: string) {
  const normalized = markdown.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return [<p key="empty">正在等待内容生成...</p>];
  }

  const lines = normalized.split("\n");
  const elements: ReactNode[] = [];
  let index = 0;
  let key = 0;

  while (index < lines.length) {
    const trimmed = lines[index].trim();
    if (!trimmed) {
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

    if (/^#{1,3}\s+/.test(trimmed)) {
      const level = trimmed.match(/^#+/)?.[0].length ?? 1;
      const content = trimmed.replace(/^#{1,3}\s+/, "");
      if (level === 1) {
        elements.push(<h1 key={`h1-${key++}`}>{renderInline(content)}</h1>);
      } else if (level === 2) {
        elements.push(<h2 key={`h2-${key++}`}>{renderInline(content)}</h2>);
      } else {
        elements.push(<h3 key={`h3-${key++}`}>{renderInline(content)}</h3>);
      }
      index += 1;
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
      if (!current || /^#{1,3}\s+/.test(current) || /^[-*]\s+/.test(current) || /^\d+\.\s+/.test(current) || current.startsWith("```")) {
        break;
      }
      paragraphLines.push(current);
      index += 1;
    }
    elements.push(<p key={`p-${key++}`}>{renderInline(paragraphLines.join(" "))}</p>);
  }

  return elements;
}

export function ConsolePage() {
  const [goal, setGoal] = useState("请用中文总结这个项目的主要能力，并给出后续优化建议。");
  const [constraints, setConstraints] = useState("输出使用 Markdown\n内容尽量简洁\n优先突出 AI Agent 能力");
  const [sourceText, setSourceText] = useState("请重点说明任务规划、步骤执行、记忆检索和运行配置这几个方面。");
  const [memoryScope, setMemoryScope] = useState("default");
  const [enableWebSearch, setEnableWebSearch] = useState(true);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [memoryQuery, setMemoryQuery] = useState("项目总结");
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [statusText, setStatusText] = useState("准备就绪，可以发起新任务。");
  const [thinkingSummary, setThinkingSummary] = useState("任务开始后，这里会显示模型当前的阶段说明和执行进度。");
  const [renderedResult, setRenderedResult] = useState("");
  const [systemCollapsed, setSystemCollapsed] = useState(false);
  const [copyText, setCopyText] = useState("复制回答");

  const resultRef = useRef<HTMLDivElement | null>(null);
  const resultTargetRef = useRef("");
  const copyTimerRef = useRef<number | null>(null);

  const refreshTasks = async () => {
    const taskItems = await listTasks();
    setTasks(taskItems);
    setCurrentTask((active) => active ?? taskItems[0] ?? null);
  };

  const refreshMemories = async () => {
    const memoryItems = await searchMemories(memoryQuery, memoryScope);
    setMemories(memoryItems);
  };

  useEffect(() => {
    void refreshTasks();
    void refreshMemories();
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
      timer = window.setTimeout(tick, 16);
    };

    timer = window.setTimeout(tick, 16);
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
  }, [renderedResult]);

  useEffect(
    () => () => {
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
    },
    [],
  );

  const runTask = async () => {
    setStatusText("任务已提交，正在启动执行流程...");
    setThinkingSummary("正在创建任务并准备连接实时进度流。");
    setRenderedResult("");

    const task = await launchTask({
      goal,
      constraints: constraints
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
      expected_output: "markdown",
      source_text: sourceText,
      memory_scope: memoryScope,
      enable_web_search: enableWebSearch,
    });

    setCurrentTask(task);
    setStatusText(`任务已启动，当前状态：${toChineseStatus(task.status)}`);
    setThinkingSummary("已连接到任务流，正在等待第一条进度更新。");

    const source = streamTask(task.id, {
      onUpdate: (nextTask) => {
        setCurrentTask(nextTask);
        const latestProgress = nextTask.progress_updates[nextTask.progress_updates.length - 1];
        if (latestProgress) {
          setThinkingSummary(
            latestProgress.detail
              ? `${latestProgress.message}\n\n${latestProgress.detail}`
              : latestProgress.message,
          );
        }

        setStatusText(
          nextTask.status === "COMPLETED"
            ? "任务已完成，可以查看结果。"
            : nextTask.status === "FAILED"
              ? "任务执行失败，请检查结果与日志。"
              : nextTask.live_result
                ? `任务执行中，当前状态：${toChineseStatus(nextTask.status)}，回答正在生成...`
                : `任务执行中，当前状态：${toChineseStatus(nextTask.status)}`,
        );

        if (["COMPLETED", "FAILED", "CANCELLED"].includes(nextTask.status)) {
          void refreshTasks();
          void refreshMemories();
          source.close();
        }
      },
      onError: () => {
        setStatusText("实时进度流已中断，请刷新页面后重试。");
      },
    });
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

  const isStreaming = Boolean(
    currentTask &&
      !["COMPLETED", "FAILED", "CANCELLED"].includes(currentTask.status) &&
      currentTask.live_result,
  );

  const markdownNodes = useMemo(() => renderMarkdownBlocks(renderedResult), [renderedResult]);

  return (
    <>
      <section className="grid">
        <section className="panel">
          <h2>发起任务</h2>
          <div className="stack">
            <label>
              任务目标
              <textarea value={goal} onChange={(event) => setGoal(event.target.value)} />
            </label>
            <label>
              约束条件
              <textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} />
            </label>
            <label>
              参考文本
              <textarea value={sourceText} onChange={(event) => setSourceText(event.target.value)} />
            </label>
            <div className="row">
              <label>
                记忆作用域
                <input value={memoryScope} onChange={(event) => setMemoryScope(event.target.value)} />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={enableWebSearch}
                  onChange={(event) => setEnableWebSearch(event.target.checked)}
                />
                启用 Web 搜索
              </label>
            </div>
            <div className="actions">
              <button onClick={() => void runTask()}>运行任务</button>
              <button className="secondary" onClick={() => void refreshTasks()}>
                刷新历史
              </button>
              <span className="meta">{statusText}</span>
            </div>
          </div>
        </section>

        <section className="panel">
          <h2>对话控制台</h2>
          <div className="meta">
            {currentTask ? `${currentTask.id} | ${toChineseStatus(currentTask.status)}` : "当前还没有选中的任务。"}
          </div>

          <section className="conversation-panel">
            <div className="conversation-header">
              <div>
                <strong>系统进度</strong>
                <div className="meta">持续展示当前阶段、步骤与执行状态</div>
              </div>
              <button className="toolbar-button secondary-button" onClick={() => setSystemCollapsed((prev) => !prev)}>
                {systemCollapsed ? "展开系统进度" : "折叠系统进度"}
              </button>
            </div>

            {!systemCollapsed ? (
              <>
                <article className="system-progress-card">
                  <strong>阶段说明</strong>
                  <p>{thinkingSummary}</p>
                </article>
                <div className="timeline">
                  {currentTask?.steps.map((step, index) => (
                    <article className="timeline-item" key={step.id}>
                      <div className="timeline-rail">
                        <span className={`timeline-dot timeline-dot-${step.status.toLowerCase()}`} />
                        {index < (currentTask.steps.length - 1) ? <span className="timeline-line" /> : null}
                      </div>
                      <div className="timeline-card">
                        <div className="timeline-head">
                          <strong>{toChineseStepName(step.name)}</strong>
                          <span className="timeline-status">{toChineseStatus(step.status)}</span>
                        </div>
                        <div className="timeline-desc">{step.description}</div>
                        {step.output ? <pre>{step.output}</pre> : <div className="meta">等待该步骤输出...</div>}
                      </div>
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <div className="meta">系统进度已折叠，你可以专注查看回答生成区。</div>
            )}
          </section>

          <section className="conversation-panel">
            <div className="conversation-header">
              <div>
                <strong>回答生成</strong>
                <div className="meta">使用 Markdown 渲染，并按流式节奏持续更新</div>
              </div>
              <div className="toolbar-actions">
                <button className="toolbar-button secondary-button" onClick={() => void handleCopyAnswer()}>
                  {copyText}
                </button>
                {isStreaming ? (
                  <span className="typing-badge">
                    <span className="typing-dot" />
                    正在生成中
                  </span>
                ) : null}
              </div>
            </div>

            <div className="assistant-bubble-shell">
              <div className="assistant-avatar">AI</div>
              <div
                ref={resultRef}
                className={isStreaming ? "assistant-bubble markdown-result result-streaming" : "assistant-bubble markdown-result"}
              >
                {markdownNodes}
                {isStreaming ? <span className="typing-caret" aria-hidden="true" /> : null}
                {!renderedResult ? <p className="meta">回答生成后会显示在这里。</p> : null}
              </div>
            </div>
          </section>
        </section>
      </section>

      <section className="grid">
        <section className="panel">
          <h2>最近任务</h2>
          <div className="list">
            {tasks.map((task) => (
              <article className="card clickable" key={task.id} onClick={() => setCurrentTask(task)}>
                <h3>{task.title}</h3>
                <div className="meta">{task.id}</div>
                <div className="meta">{toChineseStatus(task.status)}</div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>记忆检索</h2>
          <div className="actions">
            <input
              value={memoryQuery}
              onChange={(event) => setMemoryQuery(event.target.value)}
              placeholder="输入要检索的记忆关键词"
            />
            <button onClick={() => void refreshMemories()}>检索</button>
          </div>
          <div className="list" style={{ marginTop: 16 }}>
            {memories.map((memory) => (
              <article className="card" key={memory.id}>
                <h3>{memory.topic}</h3>
                <div className="meta">
                  {memory.scope} | {new Date(memory.created_at).toLocaleString()}
                </div>
                <pre>{memory.summary}</pre>
              </article>
            ))}
          </div>
        </section>
      </section>
    </>
  );
}

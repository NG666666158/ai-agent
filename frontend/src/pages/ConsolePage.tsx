import { useEffect, useState } from "react";

import { createTask, listTasks, searchMemories, type MemoryRecord, type Task } from "../api";

export function ConsolePage() {
  const [goal, setGoal] = useState("Build the Orion Agent MVP with a formal frontend and vector memory.");
  const [constraints, setConstraints] = useState(
    "Keep the flow demo-friendly\nPreserve automated tests\nReturn markdown output",
  );
  const [sourceText, setSourceText] = useState(
    "Prioritize the formal frontend app, production runtime settings, and durable long-term memory retrieval.",
  );
  const [memoryScope, setMemoryScope] = useState("default");
  const [enableWebSearch, setEnableWebSearch] = useState(true);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [memoryQuery, setMemoryQuery] = useState("frontend memory");
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [statusText, setStatusText] = useState("Ready to run the next task.");

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

  const runTask = async () => {
    setStatusText("Running task...");
    const task = await createTask({
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
    setStatusText(`Task completed with status ${task.status}.`);
    await refreshTasks();
    await refreshMemories();
  };

  return (
    <>
      <section className="grid">
        <section className="panel">
          <h2>Launch task</h2>
          <div className="stack">
            <label>
              Goal
              <textarea value={goal} onChange={(event) => setGoal(event.target.value)} />
            </label>
            <label>
              Constraints
              <textarea
                value={constraints}
                onChange={(event) => setConstraints(event.target.value)}
              />
            </label>
            <label>
              Source text
              <textarea
                value={sourceText}
                onChange={(event) => setSourceText(event.target.value)}
              />
            </label>
            <div className="row">
              <label>
                Memory scope
                <input
                  value={memoryScope}
                  onChange={(event) => setMemoryScope(event.target.value)}
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={enableWebSearch}
                  onChange={(event) => setEnableWebSearch(event.target.checked)}
                />
                Enable web search
              </label>
            </div>
            <div className="actions">
              <button onClick={() => void runTask()}>Run task</button>
              <button className="secondary" onClick={() => void refreshTasks()}>
                Refresh history
              </button>
              <span className="meta">{statusText}</span>
            </div>
          </div>
        </section>

        <section className="panel">
          <h2>Execution trace</h2>
          <div className="meta">
            {currentTask ? `${currentTask.id} · ${currentTask.status}` : "No task selected yet."}
          </div>
          <div className="steps">
            {currentTask?.steps.map((step) => (
              <article className="step" key={step.id}>
                <strong>{step.name}</strong>
                <div>{step.description}</div>
                <div className="meta">{step.status}</div>
                {step.output ? <pre>{step.output}</pre> : null}
              </article>
            ))}
          </div>
          <pre className="result">{currentTask?.result ?? "Task output will appear here."}</pre>
        </section>
      </section>

      <section className="grid">
        <section className="panel">
          <h2>Recent tasks</h2>
          <div className="list">
            {tasks.map((task) => (
              <article className="card clickable" key={task.id} onClick={() => setCurrentTask(task)}>
                <h3>{task.title}</h3>
                <div className="meta">{task.id}</div>
                <div className="meta">{task.status}</div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>Memory recall</h2>
          <div className="actions">
            <input
              value={memoryQuery}
              onChange={(event) => setMemoryQuery(event.target.value)}
              placeholder="Search memories"
            />
            <button onClick={() => void refreshMemories()}>Search</button>
          </div>
          <div className="list" style={{ marginTop: 16 }}>
            {memories.map((memory) => (
              <article className="card" key={memory.id}>
                <h3>{memory.topic}</h3>
                <div className="meta">
                  {memory.scope} · {new Date(memory.created_at).toLocaleString()}
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

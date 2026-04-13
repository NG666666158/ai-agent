import { useEffect, useState } from "react";

type Task = {
  id: string;
  title: string;
  status: string;
  result: string | null;
  steps: Array<{ id: string; name: string; status: string; description: string; output: string | null }>;
};

type Memory = {
  id: string;
  topic: string;
  scope: string;
  summary: string;
  created_at: string;
  tags: string[];
};

type RuntimeInfo = {
  openai_model: string;
  embedding_model: string;
  force_fallback_llm: boolean;
  allow_online_search: boolean;
  web_search_provider: string;
  web_search_endpoint: string;
  web_search_max_results: number;
};

type HealthInfo = {
  llm_mode: string;
  search_mode: string;
  vector_backend: string;
  tools: string[];
};

type View = "console" | "tasks" | "memories" | "settings";

const navItems: Array<{ id: View; label: string }> = [
  { id: "console", label: "Console" },
  { id: "tasks", label: "Tasks" },
  { id: "memories", label: "Memories" },
  { id: "settings", label: "Settings" },
];

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function App() {
  const [view, setView] = useState<View>("console");
  const [goal, setGoal] = useState("继续实现 AI Agent MVP，完善前端、工具和记忆能力。");
  const [constraints, setConstraints] = useState("聚焦可演示 MVP\n保证可测试回退\n输出 markdown");
  const [sourceText, setSourceText] = useState("优先完成正式前端工程、向量检索记忆和生产配置。");
  const [memoryScope, setMemoryScope] = useState("default");
  const [enableWebSearch, setEnableWebSearch] = useState(true);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [memoryQuery, setMemoryQuery] = useState("mvp");
  const [memories, setMemories] = useState<Memory[]>([]);
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [statusText, setStatusText] = useState("等待任务执行。");

  const loadTasks = async () => {
    const data = await api<Task[]>("/api/tasks");
    setTasks(data);
    if (!currentTask && data.length > 0) {
      setCurrentTask(data[0]);
    }
  };

  const loadMemories = async () => {
    const data = await api<Memory[]>(`/api/memories/search?query=${encodeURIComponent(memoryQuery)}&scope=${encodeURIComponent(memoryScope)}`);
    setMemories(data);
  };

  const loadSettings = async () => {
    const runtimeData = await api<RuntimeInfo>("/api/system/runtime");
    const healthData = await api<HealthInfo>("/api/system/health");
    setRuntime(runtimeData);
    setHealth(healthData);
  };

  useEffect(() => {
    void loadTasks();
    void loadMemories();
    void loadSettings();
  }, []);

  const runTask = async () => {
    setStatusText("任务执行中，请稍候...");
    const task = await api<Task>("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        goal,
        constraints: constraints.split("\n").map((line) => line.trim()).filter(Boolean),
        expected_output: "markdown",
        source_text: sourceText,
        memory_scope: memoryScope,
        enable_web_search: enableWebSearch,
      }),
    });
    setCurrentTask(task);
    setStatusText(`任务已完成：${task.status}`);
    await loadTasks();
    await loadMemories();
    await loadSettings();
  };

  return (
    <div className="shell">
      <section className="hero">
        <div className="eyebrow">Orion Agent Frontend</div>
        <h1>正式前端工程已接入</h1>
        <p className="sub">这套 React + Vite 前端用于驱动 Orion Agent 的任务控制台、记忆中心和运行配置页。</p>
        <nav className="nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? "nav-button active" : "nav-button"}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </section>

      {view === "console" && (
        <section className="grid">
          <section className="panel">
            <h2>发起任务</h2>
            <div className="stack">
              <label>任务目标<textarea value={goal} onChange={(e) => setGoal(e.target.value)} /></label>
              <label>约束条件<textarea value={constraints} onChange={(e) => setConstraints(e.target.value)} /></label>
              <label>参考文本<textarea value={sourceText} onChange={(e) => setSourceText(e.target.value)} /></label>
              <div className="row">
                <label>记忆作用域<input value={memoryScope} onChange={(e) => setMemoryScope(e.target.value)} /></label>
                <label className="checkbox"><input type="checkbox" checked={enableWebSearch} onChange={(e) => setEnableWebSearch(e.target.checked)} />启用 Web 搜索</label>
              </div>
              <div className="actions">
                <button onClick={() => void runTask()}>运行任务</button>
                <button className="secondary" onClick={() => void loadTasks()}>刷新历史</button>
                <span className="meta">{statusText}</span>
              </div>
            </div>
          </section>
          <section className="panel">
            <h2>结果与执行轨迹</h2>
            <div className="meta">{currentTask ? `${currentTask.id} · ${currentTask.status}` : "还没有任务结果。"}</div>
            <div className="steps">
              {currentTask?.steps.map((step) => (
                <div className="step" key={step.id}>
                  <strong>{step.name}</strong> · {step.status}
                  <div>{step.description}</div>
                  {step.output ? <pre>{step.output}</pre> : null}
                </div>
              ))}
            </div>
            <pre className="result">{currentTask?.result ?? "在这里查看生成结果。"}</pre>
          </section>
        </section>
      )}

      {view === "tasks" && (
        <section className="panel">
          <h2>任务列表</h2>
          <div className="list">
            {tasks.map((task) => (
              <article className="card clickable" key={task.id} onClick={() => setCurrentTask(task)}>
                <h3>{task.title}</h3>
                <div className="meta">{task.id} · {task.status}</div>
                <pre>{task.result ?? "No result"}</pre>
              </article>
            ))}
          </div>
        </section>
      )}

      {view === "memories" && (
        <section className="panel">
          <h2>向量检索记忆库</h2>
          <div className="actions">
            <input value={memoryQuery} onChange={(e) => setMemoryQuery(e.target.value)} />
            <input value={memoryScope} onChange={(e) => setMemoryScope(e.target.value)} />
            <button onClick={() => void loadMemories()}>检索</button>
          </div>
          <div className="list" style={{ marginTop: 16 }}>
            {memories.map((memory) => (
              <article className="card" key={memory.id}>
                <h3>{memory.topic}</h3>
                <div className="meta">{memory.scope} · {memory.created_at}</div>
                <pre>{memory.summary}\n\nTags: {memory.tags.join(", ")}</pre>
              </article>
            ))}
          </div>
        </section>
      )}

      {view === "settings" && (
        <section className="grid">
          <section className="panel">
            <h2>运行时配置</h2>
            <pre>{runtime ? JSON.stringify(runtime, null, 2) : "Loading..."}</pre>
          </section>
          <section className="panel">
            <h2>系统健康</h2>
            <pre>{health ? JSON.stringify(health, null, 2) : "Loading..."}</pre>
          </section>
        </section>
      )}
    </div>
  );
}

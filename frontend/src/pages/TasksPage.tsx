import { useEffect, useState } from "react";

import { getTaskEvaluation, listTasks, type Evaluation, type Task } from "../api";

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
  };
  return mapping[status] ?? status;
}

export function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);

  useEffect(() => {
    void (async () => {
      const taskItems = await listTasks();
      setTasks(taskItems);
      const firstTask = taskItems[0] ?? null;
      setSelectedTask(firstTask);
      if (firstTask) {
        setEvaluation(await getTaskEvaluation(firstTask.id));
      }
    })();
  }, []);

  const inspectTask = async (task: Task) => {
    setSelectedTask(task);
    setEvaluation(await getTaskEvaluation(task.id));
  };

  return (
    <section className="grid">
      <section className="panel">
        <h2>任务列表</h2>
        <div className="list">
          {tasks.map((task) => (
            <article className="card clickable" key={task.id} onClick={() => void inspectTask(task)}>
              <h3>{task.title}</h3>
              <div className="meta">{toChineseStatus(task.status)}</div>
              <div className="meta">{task.id}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>当前任务</h2>
        {selectedTask ? (
          <>
            <div className="meta">
              {selectedTask.id} | {toChineseStatus(selectedTask.status)}
            </div>
            <pre className="result">{selectedTask.result ?? "暂无结果"}</pre>
            <div className="metric-grid">
              <article className="metric-card">
                <span>质量评分</span>
                <strong>{evaluation?.score?.toFixed(2) ?? "..."}</strong>
              </article>
              <article className="metric-card">
                <span>步骤数量</span>
                <strong>{selectedTask.steps.length}</strong>
              </article>
            </div>
            <div className="list">
              {(evaluation?.checks ?? []).map((item) => (
                <article className="card" key={item}>
                  <pre>{item}</pre>
                </article>
              ))}
            </div>
          </>
        ) : (
          <div className="meta">当前还没有任务。</div>
        )}
      </section>
    </section>
  );
}

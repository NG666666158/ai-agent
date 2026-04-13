import { useEffect, useState } from "react";

import { getTaskEvaluation, listTasks, type Evaluation, type Task } from "../api";

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
        <h2>Task registry</h2>
        <div className="list">
          {tasks.map((task) => (
            <article className="card clickable" key={task.id} onClick={() => void inspectTask(task)}>
              <h3>{task.title}</h3>
              <div className="meta">{task.status}</div>
              <div className="meta">{task.id}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Selected task</h2>
        {selectedTask ? (
          <>
            <div className="meta">
              {selectedTask.id} · {selectedTask.status}
            </div>
            <pre className="result">{selectedTask.result ?? "No result"}</pre>
            <div className="metric-grid">
              <article className="metric-card">
                <span>Quality score</span>
                <strong>{evaluation?.score?.toFixed(2) ?? "..."}</strong>
              </article>
              <article className="metric-card">
                <span>Steps</span>
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
          <div className="meta">No task available yet.</div>
        )}
      </section>
    </section>
  );
}

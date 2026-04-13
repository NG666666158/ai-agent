async function loadTasksPage() {
  const tasks = await fetchJson('/api/tasks');
  const container = document.getElementById('taskList');
  container.innerHTML = '';
  for (const task of tasks) {
    const evaluation = await fetchJson(`/api/tasks/${task.id}/evaluation`);
    const card = document.createElement('article');
    card.className = 'card';
    card.innerHTML = `
      <h3>${task.title}</h3>
      <div class="meta">${task.id} · ${task.status}</div>
      <div class="meta" style="margin-top:8px;">质量得分：${evaluation.score.toFixed(2)}</div>
      <pre>${task.result || 'No result'}</pre>
    `;
    container.appendChild(card);
  }
}

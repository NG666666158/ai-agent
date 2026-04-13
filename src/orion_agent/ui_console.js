async function loadConsoleData() {
  const tasks = await fetchJson('/api/tasks');
  const container = document.getElementById('taskHistory');
  container.innerHTML = '';
  tasks.forEach(task => {
    const card = document.createElement('article');
    card.className = 'card clickable';
    card.innerHTML = `<h3>${task.title}</h3><div class="meta">${task.id} · ${task.status}</div>`;
    card.onclick = () => renderTask(task);
    container.appendChild(card);
  });
}

function renderTask(task) {
  document.getElementById('resultMeta').textContent = `任务 ${task.id} · 状态 ${task.status} · 步骤 ${task.steps.length}`;
  document.getElementById('resultBox').textContent = task.result || '没有结果';
  const stepList = document.getElementById('stepList');
  stepList.innerHTML = '';
  task.steps.forEach(step => {
    const el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = `<strong>${step.name}</strong> · ${step.status}<br>${step.description}${step.output ? `<pre>${step.output}</pre>` : ''}`;
    stepList.appendChild(el);
  });
}

async function searchMemories() {
  const query = document.getElementById('memoryQuery').value;
  const scope = document.getElementById('memoryScope').value || 'default';
  const memories = await fetchJson(`/api/memories/search?query=${encodeURIComponent(query)}&scope=${encodeURIComponent(scope)}`);
  const container = document.getElementById('memoryResults');
  container.innerHTML = '';
  memories.forEach(item => {
    const card = document.createElement('article');
    card.className = 'card';
    card.innerHTML = `<h3>${item.topic}</h3><div class="meta">${item.scope} · ${item.created_at}</div><pre>${item.summary}</pre>`;
    container.appendChild(card);
  });
  if (!memories.length) {
    container.innerHTML = '<div class="meta">没有检索到相关长期记忆。</div>';
  }
}

function getPayload() {
  return {
    goal: document.getElementById('goal').value,
    constraints: document.getElementById('constraints').value.split('\n').map(v => v.trim()).filter(Boolean),
    expected_output: document.getElementById('expectedOutput').value,
    source_text: document.getElementById('sourceText').value,
    memory_scope: document.getElementById('memoryScope').value || 'default',
    enable_web_search: document.getElementById('enableWebSearch').checked,
  };
}

async function runTask() {
  const statusText = document.getElementById('statusText');
  statusText.textContent = '任务执行中，请稍候...';
  const task = await fetchJson('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(getPayload()),
  });
  renderTask(task);
  statusText.textContent = `任务已完成：${task.status}`;
  await loadConsoleData();
  await searchMemories();
}

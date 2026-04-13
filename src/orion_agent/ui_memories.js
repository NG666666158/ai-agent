async function searchMemoryPage() {
  const query = document.getElementById('memoryQuery').value;
  const scope = document.getElementById('memoryScope').value || 'default';
  const memories = await fetchJson(`/api/memories/search?query=${encodeURIComponent(query)}&scope=${encodeURIComponent(scope)}`);
  const container = document.getElementById('memoryList');
  container.innerHTML = '';
  memories.forEach(item => {
    const card = document.createElement('article');
    card.className = 'card';
    card.innerHTML = `<h3>${item.topic}</h3><div class="meta">${item.scope}</div><pre>${item.summary}\n\nTags: ${(item.tags || []).join(', ')}</pre>`;
    container.appendChild(card);
  });
  if (!memories.length) {
    container.innerHTML = '<div class="meta">没有检索到相关记忆。</div>';
  }
}

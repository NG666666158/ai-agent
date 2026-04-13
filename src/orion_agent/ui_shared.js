async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function renderNav(activePath) {
  const links = [
    ['/', 'Console'],
    ['/tasks', 'Tasks'],
    ['/memories', 'Memories'],
    ['/settings', 'Settings'],
  ];
  return `
    <nav class="nav">
      ${links.map(([href, label]) => `<a href="${href}" class="${activePath === href ? 'active' : ''}">${label}</a>`).join('')}
    </nav>
  `;
}

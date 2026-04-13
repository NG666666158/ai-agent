async function loadSettingsPage() {
  const runtime = await fetchJson('/api/system/runtime');
  const health = await fetchJson('/api/system/health');
  document.getElementById('runtimeBox').textContent = JSON.stringify(runtime, null, 2);
  document.getElementById('healthBox').textContent = JSON.stringify(health, null, 2);
}

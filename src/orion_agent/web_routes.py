from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response


router = APIRouter(tags=["ui"])
BASE_DIR = Path(__file__).resolve().parent


def _read_asset(filename: str) -> str:
    path = BASE_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Asset not found: {filename}")
    return path.read_text(encoding="utf-8")


def _page(title: str, active_path: str, body: str, script_name: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="/assets/ui_styles.css" />
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Orion Agent Console</div>
      <h1>{title}</h1>
      <div class="sub">独立页面化的前端控制台，用于演示任务执行、长期记忆、评估结果和运行配置。</div>
      <div id="nav"></div>
    </section>
    {body}
  </main>
  <script src="/assets/ui_shared.js"></script>
  <script>document.getElementById('nav').innerHTML = renderNav('{active_path}');</script>
  <script src="/assets/{script_name}"></script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
def home() -> str:
    body = """
    <section class="grid">
      <section class="panel">
        <h2>发起任务</h2>
        <div class="stack">
          <div><label for="goal">任务目标</label><textarea id="goal">继续实现 AI Agent MVP，完善前端、工具和记忆能力。</textarea></div>
          <div><label for="constraints">约束条件（每行一个）</label><textarea id="constraints">聚焦可演示 MVP
保证可测试回退
输出 markdown</textarea></div>
          <div><label for="sourceText">参考文本</label><textarea id="sourceText">优先完成最小前端控制台、增强 LLM 策略、优化长期记忆，再补测试和代码审核。</textarea></div>
          <div class="row">
            <div><label for="memoryScope">记忆作用域</label><input id="memoryScope" value="default" /></div>
            <div><label for="expectedOutput">输出格式</label><select id="expectedOutput"><option value="markdown" selected>markdown</option><option value="json">json</option></select></div>
          </div>
          <div class="row"><label><input id="enableWebSearch" type="checkbox" checked /> 启用 Web 搜索</label></div>
          <div class="actions"><button id="runTask">运行任务</button><button id="refreshTasks" class="secondary">刷新历史</button><span class="meta" id="statusText">等待任务执行。</span></div>
        </div>
      </section>
      <section class="panel">
        <h2>结果与执行轨迹</h2>
        <div id="resultMeta" class="meta">还没有任务结果。</div>
        <div class="steps" id="stepList"></div>
        <pre id="resultBox" class="result">在这里查看生成结果。</pre>
      </section>
    </section>
    <section class="grid">
      <section class="panel"><h2>任务历史</h2><div class="list" id="taskHistory"></div></section>
      <section class="panel">
        <h2>长期记忆搜索</h2>
        <div class="actions" style="margin-top:0"><input id="memoryQuery" value="mvp" /><button id="searchMemory">检索记忆</button></div>
        <div class="list" id="memoryResults" style="margin-top:14px"></div>
      </section>
    </section>
    <script>
      document.getElementById('runTask').addEventListener('click', runTask);
      document.getElementById('refreshTasks').addEventListener('click', loadConsoleData);
      document.getElementById('searchMemory').addEventListener('click', searchMemories);
      loadConsoleData();
      searchMemories();
    </script>
    """
    return _page("Console", "/", body, "ui_console.js")


@router.get("/tasks", response_class=HTMLResponse)
def tasks_page() -> str:
    body = """
    <section class="panel">
      <h2>任务列表与质量评估</h2>
      <div class="list" id="taskList"></div>
    </section>
    <script>loadTasksPage();</script>
    """
    return _page("Tasks", "/tasks", body, "ui_tasks.js")


@router.get("/memories", response_class=HTMLResponse)
def memories_page() -> str:
    body = """
    <section class="panel">
      <h2>向量检索记忆库</h2>
      <div class="actions"><input id="memoryQuery" value="agent roadmap" /><input id="memoryScope" value="default" /><button id="searchMemoryButton">检索</button></div>
      <div class="list" id="memoryList" style="margin-top:14px"></div>
    </section>
    <script>
      document.getElementById('searchMemoryButton').addEventListener('click', searchMemoryPage);
      searchMemoryPage();
    </script>
    """
    return _page("Memories", "/memories", body, "ui_memories.js")


@router.get("/settings", response_class=HTMLResponse)
def settings_page() -> str:
    body = """
    <section class="grid">
      <section class="panel">
        <h2>运行时配置</h2>
        <pre id="runtimeBox">Loading...</pre>
      </section>
      <section class="panel">
        <h2>系统健康</h2>
        <pre id="healthBox">Loading...</pre>
      </section>
    </section>
    <script>loadSettingsPage();</script>
    """
    return _page("Settings", "/settings", body, "ui_settings.js")


@router.get("/assets/{filename}")
def asset(filename: str) -> Response:
    content = _read_asset(filename)
    media_type = "text/plain"
    if filename.endswith(".css"):
        media_type = "text/css"
    elif filename.endswith(".js"):
        media_type = "application/javascript"
    elif filename.endswith(".html"):
        media_type = "text/html"
    return Response(content=content, media_type=media_type)

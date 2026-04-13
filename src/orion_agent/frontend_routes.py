from __future__ import annotations

from mimetypes import guess_type
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse


router = APIRouter(tags=["frontend"], include_in_schema=False)
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
SPA_PATHS = {"", "/", "tasks", "memories", "settings"}


def _frontend_index() -> Path:
  return FRONTEND_DIST / "index.html"


def _fallback_page() -> str:
  return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Orion Agent Frontend</title>
</head>
<body style="font-family:Segoe UI,sans-serif;padding:32px;background:#f8fafc;color:#0f172a">
  <h1>Orion Agent frontend build is not available yet</h1>
  <p>Run <code>npm install</code> and <code>npm run build</code> inside <code>frontend/</code>, then refresh this page.</p>
</body>
</html>"""


@router.get("/{path:path}")
def frontend(path: str = ""):
  normalized = path.strip("/")
  requested_file = FRONTEND_DIST / normalized

  if normalized and requested_file.is_file():
    media_type, _ = guess_type(str(requested_file))
    return FileResponse(requested_file, media_type=media_type)

  if normalized in SPA_PATHS or not normalized or "." not in normalized:
    index_file = _frontend_index()
    if index_file.exists():
      return FileResponse(index_file, media_type="text/html")
    return HTMLResponse(_fallback_page())

  raise HTTPException(status_code=404, detail="Frontend asset not found")

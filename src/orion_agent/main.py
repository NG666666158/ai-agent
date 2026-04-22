from fastapi import FastAPI, Request

from orion_agent.api.routes.memories import router as memories_router
from orion_agent.api.routes.sessions import router as sessions_router
from orion_agent.api.routes.system import router as system_router
from orion_agent.api.routes.tasks import router as tasks_router
from orion_agent.frontend_routes import router as frontend_router


app = FastAPI(
    title="Orion Agent MVP",
    version="0.1.0",
    description="Single-agent MVP for planning and delivering structured task results.",
)


@app.middleware("http")
async def ensure_utf8_for_json(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json") and "charset=" not in content_type:
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(tasks_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(memories_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(frontend_router)

from fastapi import FastAPI

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


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(tasks_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(memories_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(frontend_router)

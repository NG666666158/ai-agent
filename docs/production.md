# Orion Agent production notes

## What is included

- FastAPI application service on port `8011`
- React + Vite frontend built into `frontend/dist`
- Qdrant as the vector database
- Prometheus scraping `/api/system/metrics`
- Grafana preconfigured with Prometheus as the default datasource

## Local stack bootstrap

1. Copy `deploy/.env.example` to `deploy/.env`.
2. Fill in `OPENAI_API_KEY` when online LLM and embedding mode is required.
3. Run `powershell -ExecutionPolicy Bypass -File deploy/start-stack.ps1`.

## Important environment variables

- `VECTOR_BACKEND=qdrant`
- `VECTOR_SERVICE_URL=http://qdrant:6333`
- `VECTOR_COLLECTION=orion_agent_memories`
- `VECTOR_DIMENSIONS=1536`
- `ALLOW_ONLINE_SEARCH=true`
- `AGENT_FORCE_FALLBACK=false`

## Monitoring endpoints

- App health: `GET /api/system/health`
- Runtime config: `GET /api/system/runtime`
- Metrics: `GET /api/system/metrics`

## Local non-container workflow

Run `powershell -ExecutionPolicy Bypass -File deploy/start-local.ps1` to install backend and frontend dependencies, build the frontend, and boot the FastAPI service.

# Orion Agent production notes

## What is included

- FastAPI application service on port `8011`
- React + Vite frontend built into `frontend/dist`
- Qdrant as the vector database
- Prometheus scraping `/api/system/metrics`
- Grafana preconfigured with Prometheus as the default datasource

## Local stack bootstrap

1. Copy `deploy/.env.example` to `deploy/.env`.
2. Choose the provider you want in `deploy/.env`.
3. For OpenAI mode, keep `LLM_PROVIDER=openai` and fill in `OPENAI_API_KEY`.
4. For MiniMax mode, set `LLM_PROVIDER=minimax` and fill in `MINIMAX_API_KEY`.
5. MiniMax uses the Anthropic-compatible endpoint from the official quickstart:
   `MINIMAX_BASE_URL=https://api.minimaxi.com/anthropic`
6. Run `powershell -ExecutionPolicy Bypass -File deploy/start-stack.ps1`.
7. Keep secrets only in `deploy/.env`; never commit a real key into `deploy/.env.example`.

## Important environment variables

- `LLM_PROVIDER=minimax`
- `MINIMAX_API_KEY=your_token_plan_key`
- `MINIMAX_MODEL=MiniMax-M2.7`
- `MINIMAX_BASE_URL=https://api.minimaxi.com/anthropic`
- `MINIMAX_MAX_RETRIES=1`
- `VECTOR_BACKEND=qdrant`
- `VECTOR_SERVICE_URL=http://qdrant:6333`
- `VECTOR_COLLECTION=orion_agent_memories`
- `VECTOR_DIMENSIONS=1536`
- `ALLOW_ONLINE_SEARCH=true`
- `AGENT_FORCE_FALLBACK=false`

## Monitoring endpoints

- App health: `GET /api/system/health`
- Runtime config: `GET /api/system/runtime`
- LLM probe: `GET /api/system/llm-probe`
- If `perform_request=true` returns `status=error`, inspect `error_type`, `error`, and `/api/system/health.llm_last_error` to tell configuration issues from outbound-network failures.
- Metrics: `GET /api/system/metrics`

## Local non-container workflow

Run `powershell -ExecutionPolicy Bypass -File deploy/start-local.ps1` to install backend and frontend dependencies, build the frontend, and boot the FastAPI service.

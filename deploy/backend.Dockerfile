FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

RUN python -m pip install --no-cache-dir .

EXPOSE 8011

CMD ["python", "-m", "uvicorn", "--app-dir", "src", "orion_agent.main:app", "--host", "0.0.0.0", "--port", "8011"]

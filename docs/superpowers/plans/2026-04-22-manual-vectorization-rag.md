# Manual Vectorization RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add recursive/parent-doc/semantic chunking plus a visual manual vectorization workflow with preview-before-ingest.

**Architecture:** Introduce a dedicated ingestion service that converts long text into chunk previews and persisted long-term memories. Expose preview/commit APIs, then connect a fifth right-rail button in the console for interactive vectorization and optional storage.

**Tech Stack:** FastAPI, Pydantic, unittest, existing embedding/vector store stack, React 19, TypeScript, Vite

---

### Task 1: Backend ingestion models and failing tests

**Files:**
- Create: `tests/test_ingestion.py`
- Modify: `tests/test_api_v1.py`

- [x] Add unit tests for recursive chunking, parent-child preview metadata, semantic chunking output, and commit storage behavior.
- [x] Add API tests for `/api/memories/ingest/preview` and `/api/memories/ingest/commit`.

### Task 2: Backend ingestion service and API

**Files:**
- Create: `src/orion_agent/core/ingestion.py`
- Modify: `src/orion_agent/core/models.py`
- Modify: `src/orion_agent/core/runtime_agent.py`
- Modify: `src/orion_agent/api/routes/memories.py`

- [x] Add ingestion request/response models and chunk metadata fields.
- [x] Implement recursive, parent-child, and heuristic semantic chunking.
- [x] Implement preview and commit service methods.
- [x] Expose preview/commit API routes.

### Task 3: Parent-doc aware recall integration

**Files:**
- Modify: `src/orion_agent/core/memory.py`

- [x] Promote child-chunk hits back to parent documents during recall while keeping retrieval reason/channel metadata.

### Task 4: Frontend vectorization workspace

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/ConsolePage.tsx`
- Modify: `frontend/src/new-styles.css`

- [x] Add the fifth right-rail button.
- [x] Build manual vectorization form, preview panel, and confirm-ingest action.
- [x] Show chunk text, dimensions, embedding preview, and ingest result.

### Task 5: Verification

**Files:**
- Modify: `tests/test_api_v1.py`
- Modify: `tests/test_ingestion.py`

- [x] Run targeted backend tests.
- [x] Run frontend build.

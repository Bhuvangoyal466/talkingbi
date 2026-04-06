# TalkingBI

TalkingBI is a conversational Business Intelligence platform that lets users upload business data, ask questions in natural language, generate charts, discover insights, and interact using voice.

It combines:
- A FastAPI backend for orchestration, analytics, voice processing, and persistence.
- A React + Vite frontend for chat-first BI interaction.
- A layered AI pipeline that routes intent to SQL, data preparation, charting, or insight discovery modules.

## Table of Contents

1. [What the Project Solves](#what-the-project-solves)
2. [Core Features](#core-features)
3. [System Architecture](#system-architecture)
4. [Repository Structure](#repository-structure)
5. [Technology Stack](#technology-stack)
6. [Quick Start (Local)](#quick-start-local)
7. [Quick Start (Docker)](#quick-start-docker)
8. [Environment Variables](#environment-variables)
9. [API Overview](#api-overview)
10. [How the Pipeline Works](#how-the-pipeline-works)
11. [Voice Agent Flow](#voice-agent-flow)
12. [Session and Persistence Model](#session-and-persistence-model)
13. [Testing](#testing)
14. [Common Troubleshooting](#common-troubleshooting)
15. [Viva Preparation Notes](#viva-preparation-notes)

## What the Project Solves

Traditional BI tools require SQL knowledge and manual dashboard setup. TalkingBI provides a natural-language interface where users can:
- Ask analytical questions in plain English.
- Get structured responses (SQL output, charts, insights, summaries).
- Maintain conversation context per session.
- Use voice input/output for hands-free querying.

## Core Features

1. Conversational analytics with automatic intent routing.
2. File upload support for CSV, Excel, and Parquet.
3. Background knowledge-base generation after upload.
4. SQL query generation and execution through a dual-agent SQL engine.
5. Data preparation workflow (cleaning/transformation intent).
6. Chart generation with chart type selection and interactive rendering support.
7. Auto-insight discovery with parallel insight question processing.
8. KPI coverage extraction attached to responses.
9. Voice transcription, voice analysis, and text-to-speech summarization.
10. Session persistence using SQLite-backed history.

## System Architecture

TalkingBI follows a layered architecture:

1. Data Access Layer:
Discovers schema, explores tables, builds triplet knowledge base in Chroma, powers SQL retrieval.

2. Data Preparation Layer:
Uses a tree reasoner and operators to clean/transform dataframes when prep intent is detected.

3. Insight Engine Layer:
Refines goal, generates analytical questions, discovers insights, evaluates and summarizes them.

4. Visualization Layer:
Extracts chart-ready data, selects chart types, generates chart code/image and chart_data payload.

5. Orchestrator:
Routes user intent and coordinates all layers through a single pipeline entrypoint.

6. API Layer:
Exposes REST and WebSocket endpoints for chat, upload, charts, insights, voice, and session lifecycle.

7. Frontend:
Provides chat, chart, and insight views with session controls, uploads, and voice interaction.

## Repository Structure

Top-level modules:

- `api/`: FastAPI app, routes, request/response schemas.
- `core/`: config, logging, LLM client, KPI service, voice service, exceptions, session store.
- `layers/`: the four core research layers (data_access, data_prep, insight_engine, visualization).
- `orchestrator/`: main pipeline, routing logic, session manager.
- `vector_store/`: embeddings and retrieval for knowledge-base components.
- `frontend/`: React + TypeScript UI.
- `tests/`: unit, integration, API, and E2E test suites.
- `data/`: uploads, caches, persisted Chroma DB, and session SQLite files.

## Technology Stack

Backend:
- FastAPI, Uvicorn
- Pandas, DuckDB/SQLite workflows
- ChromaDB
- sentence-transformers embeddings
- LLM providers: OpenRouter, Groq, Ollama
- Voice: faster-whisper, AssemblyAI (optional), Groq Whisper (fallback), edge-tts

Frontend:
- React 18 + TypeScript
- Vite
- TanStack Query
- Tailwind + shadcn/ui patterns
- Recharts for chart rendering

Testing:
- pytest + pytest-asyncio (backend)
- Vitest + Playwright (frontend)

## Quick Start (Local)

### Prerequisites

1. Python 3.11+
2. Node.js 18+
3. npm 9+ (or equivalent)
4. ffmpeg installed (needed for voice workflows)

### 1) Clone and Install Backend

```bash
pip install -r requirements.txt
```

### 2) Configure Environment

```bash
copy .env.example .env
```

Set at least one provider key in `.env`:
- `OPENROUTER_API_KEY`, or
- `GROQ_API_KEY`

### 3) Start Backend

```bash
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 4) Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Default URLs:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

## Quick Start (Docker)

```bash
docker compose up --build
```

Services:
- API container on `http://localhost:8000`
- Frontend container on `http://localhost:3000`

## Environment Variables

Important keys (see `.env.example` for full list):

- `LLM_PROVIDER`: `groq | openrouter | ollama`
- `OPENROUTER_API_KEY`, `GROQ_API_KEY`
- `PRIMARY_MODEL`, `CODE_MODEL`
- `VOICE_USE_LOCAL_TRANSCRIPTION`
- `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`
- `TTS_VOICE`, `TTS_RATE`, `TTS_PITCH`
- `MAX_EXPLORATION_STEPS`, `N_INSIGHT_QUESTIONS`

## API Overview

Health and session:
- `GET /health`
- `POST /session/new`
- `GET /session/{session_id}/status`
- `DELETE /session/{session_id}`
- `GET /session/{session_id}/history`
- `GET /sessions/history`
- `DELETE /sessions/history/{session_id}`

Data:
- `POST /data/upload`
- `POST /data/connect-db`
- `GET /data/preview`

Analytics:
- `POST /chat`
- `POST /charts/generate`
- `POST /insights/discover`
- `GET /session/{session_id}/chart-suggestions`

Voice:
- `WS /voice/stream`
- `POST /voice/transcribe-only`
- `POST /voice/analyse`
- `POST /voice/respond`

LLM metadata:
- `GET /llm/provider`

## How the Pipeline Works

The backend core entrypoint is `TalkingBIPipeline.process(message)`.

Flow:

1. Message is stored in session history and session SQLite store.
2. QueryRouter classifies intent:
	- `sql_query`
	- `data_prep`
	- `chart`
	- `insight`
	- `hybrid`
	- `conversation`
3. Intent-specific handler executes.
4. KPI coverage is attached to the response if available.
5. Structured output is persisted (messages, charts, insights).
6. Response is returned to frontend.

Performance design choices:
- Upload is split into fast and background phases.
- Knowledge-base build runs in a thread pool executor.
- Insight question discovery runs in parallel worker threads.
- File hash is used to reuse Chroma KB collections across repeated uploads.

## Voice Agent Flow

Voice support includes two patterns:

1. WebSocket streaming endpoint (`/voice/stream`):
- Receives audio chunks
- Transcribes
- Runs pipeline process
- Returns response + optional base64 audio

2. Upload-based transcription endpoint (`/voice/transcribe-only`):
- Frontend records via MediaRecorder
- Sends blob as multipart upload
- Gets transcript text back
- Frontend sends transcript as normal chat message

Transcription fallback order in `core.voice_service`:

1. Local Whisper (if enabled and installed)
2. AssemblyAI (if key configured)
3. Groq Whisper (if key configured)

TTS:
- Uses `edge-tts` when available.
- Summary text is clipped to `VOICE_MAX_SPOKEN_WORDS`.

## Session and Persistence Model

Two levels of state:

1. In-memory runtime session:
- Managed by `SessionManager`
- Holds active `TalkingBIPipeline` per `session_id`

2. Persistent per-session SQLite store:
- Stored under `data/sessions/*.db`
- Saves messages, insights, charts, upload metadata
- Enables session history and recovery after backend restart

Upload behavior:
- File is loaded to dataframe and preview is returned quickly.
- Temporary SQLite DB is written.
- KB/SQL engine builds in background.
- `kb_ready` in status endpoint helps frontend gate query timing.

## Testing

Run backend tests:

```bash
pytest
```

Run frontend tests:

```bash
cd frontend
npm test
```

## Common Troubleshooting

1. Error: No data available.
- Upload a file first or connect DB.
- Check session status endpoint for `has_data` and `has_db`.

2. Error: KB still building.
- Wait until `kb_ready=true` from `/session/{id}/status`.

3. Voice transcription not working.
- Verify at least one provider is configured for transcription fallback.
- Check microphone permissions in browser.
- Ensure `ffmpeg` exists in system path.

4. Slow first response.
- Initial embedding/LLM warmups and KB building are expected on first run.

## Viva Preparation Notes

For feature-level, interviewer-friendly explanation, see:

- `docs/VIVA_WORKFLOW.md`

This document gives module-by-module flow, endpoint mapping, and likely viva questions with precise answers.

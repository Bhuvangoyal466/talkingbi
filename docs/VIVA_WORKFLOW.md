# TalkingBI Viva Workflow Documentation

This document explains how each major feature works end-to-end, from UI action to backend execution, in a viva-friendly format.

## 1. Project Flow in One View

TalkingBI execution path:

1. User interacts in frontend (chat, upload, chart, insights, voice).
2. Frontend calls FastAPI endpoints.
3. Orchestrator routes user request by intent.
4. Appropriate layer runs (SQL, data prep, charting, insights, conversation).
5. KPI coverage and metadata are attached.
6. Results are persisted in session SQLite store.
7. Response is rendered in frontend as text, table, chart, or insight cards.

## 2. Feature-by-Feature Workflow

### A. Session Creation and Lifecycle

What happens:

1. Frontend loads and requests `POST /session/new`.
2. Backend creates `TalkingBIPipeline` instance for this `session_id`.
3. Session state is held in memory through `SessionManager`.
4. Session history and analytics artifacts are persisted in `data/sessions/{session_id}.db`.

Why this design:

- Memory gives fast runtime performance.
- SQLite gives persistence across refresh/restart.

Viva one-liner:

- We use hybrid session state: in-memory for speed and SQLite for durability.

### B. Data Upload and Background KB Build

Trigger:

- User uploads CSV/Excel/Parquet from sidebar.

Backend flow:

1. `POST /data/upload` receives file and validates extension.
2. File is saved to `data/uploads/`.
3. `pipeline.load_file()` loads dataframe and returns preview immediately.
4. A temporary SQLite DB is created for SQL access.
5. Background thread starts `_build_sql_engine_bg()`.
6. Background build performs schema extraction + database exploration + triplet KB creation in Chroma.
7. SQL engine is marked ready and `kb_ready=true`.

Performance rationale:

- Upload response is fast because expensive KB creation is decoupled.
- Frontend can poll session status and avoid user confusion.

Viva one-liner:

- Upload is implemented as a two-phase pipeline: immediate preview plus asynchronous knowledge-base indexing.

### C. Chat and Intent Routing

Trigger:

- User sends natural-language message in chat box.

Flow:

1. Frontend calls `POST /chat`.
2. Backend calls `pipeline.process(message)`.
3. `QueryRouter` classifies intent using LLM JSON output with keyword fallback.
4. Based on intent, one handler executes:
   - SQL
   - Data prep
   - Chart
   - Insight
   - Hybrid
   - Conversation
5. Result is post-processed for KPI coverage.
6. Assistant summary + metadata saved in session store.
7. Structured response returned to frontend.

Viva one-liner:

- Our orchestrator is intent-driven; a single endpoint can route to specialized analytical modules.

### D. SQL Query Feature

Trigger examples:

- "Show total sales by state"
- "How many orders were placed in 2024"

Flow:

1. `_handle_sql()` checks if SQL engine is ready.
2. Dual-agent SQL engine attempts LLM-guided query synthesis and execution.
3. If generation fails, deterministic aggregate fallback is attempted for common metrics.
4. Response includes SQL text, result columns/rows, rows returned, and answer summary.

Fallback value:

- Reduces failure for common aggregation questions under LLM instability/rate limits.

Viva one-liner:

- We combine model-generated SQL with deterministic fallback to improve reliability.

### E. Data Preparation Feature

Trigger examples:

- "Clean this dataset"
- "Remove duplicates and standardize columns"

Flow:

1. `_handle_data_prep()` constructs target schema goal from user message.
2. `DeepPrepReasoner` executes transformation reasoning pipeline.
3. Updated dataframe replaces `current_df` in session.
4. Returns prep steps, new shape, columns, and preview.

Viva one-liner:

- Data prep is treated as a reasoning pipeline over dataframe transformations, not a hardcoded script.

### F. Chart Generation Feature

Trigger examples:

- "Plot revenue by month as line chart"

Flow:

1. Frontend either uses chat intent or direct `/charts/generate` API.
2. `_handle_chart()` extracts relevant series from dataframe.
3. Chart type selector chooses chart family (or uses explicit override).
4. Chart generator builds figure/code and returns base64 image + chart_data.
5. Frontend renders interactive chart when `chart_data` is available.

Returned payload highlights:

- `chart_type`
- `title`
- `image_base64`
- `code`
- `chart_data`

Viva one-liner:

- Charting pipeline is extraction first, chart-type reasoning second, rendering third.

### G. Insight Discovery Feature

Trigger examples:

- "Find key insights in this data"
- "Analyze sales pattern and anomalies"

Flow:

1. `GoalRefiner` turns user input into refined analytical goal.
2. `QuestionGenerator` creates focused sub-questions.
3. `InsightDiscoverer` processes questions in parallel thread pool.
4. `InsightEvaluator` scores and filters results.
5. `SummarySynthesizer` creates executive summary.
6. Response returns insight cards + confidence + summary.

Performance design:

- Parallel insight discovery cuts wall-clock time.

Viva one-liner:

- Insights are generated through goal decomposition and parallel analytical questioning.

### H. Hybrid Analysis Feature

Trigger examples:

- "Plot trend and explain what it means"

Flow:

1. `_handle_hybrid()` runs SQL and chart branches.
2. Also generates top insight snippets.
3. Returns unified response with data, chart, and insight text.

Viva one-liner:

- Hybrid intent composes retrieval, visualization, and interpretation in one response object.

### I. KPI Coverage Feature

Purpose:

- Attach explainability about KPI availability and match quality.

Flow:

1. Every successful handler calls `_attach_kpi_coverage()`.
2. `core.kpi_service` computes requested vs available KPI mapping.
3. Coverage object is embedded into response.
4. Frontend shows it via shared KPI card component.

Viva one-liner:

- KPI coverage improves transparency by showing what was answerable from current data.

### J. Voice Agent Feature

Available modes:

1. WebSocket real-time endpoint (`/voice/stream`).
2. Upload-transcribe endpoint (`/voice/transcribe-only`) used by current hook.

Current frontend path (`useVoiceAgent`):

1. User clicks mic button.
2. Browser records audio with `MediaRecorder`.
3. Audio blob is sent to `/voice/transcribe-only`.
4. Transcript text is returned.
5. Transcript is sent through regular chat path.

Backend transcription strategy (fallback):

1. Local Whisper (if enabled)
2. AssemblyAI (if key provided)
3. Groq Whisper

Voice response:

- `build_voice_summary()` makes concise spoken summary.
- `synthesize_voice_audio()` uses edge-tts when available.

Viva one-liner:

- Voice module is provider-resilient via multi-stage transcription fallback and optional TTS synthesis.

## 3. Frontend Flow Summary

Main UI layers:

1. Sidebar:
- Upload, quick actions, preview, session history, new session.

2. Chat view:
- Multi-type message rendering (text, sql, chart, insight, hybrid).
- Voice controls integrated.

3. Charts view:
- Direct chart generation + suggestion prompts + chart history.

4. Insights view:
- Discover insights, filter by insight type, copy summary.

State handling:

- Active session is stored in browser sessionStorage.
- Session-specific chart/insight caches are also saved in sessionStorage.
- Backend remains source of truth for session history.

## 4. Persistence and Recoverability

Stored artifacts per session:

1. Messages
2. Upload metadata
3. Chart metadata
4. Insight runs
5. KPI coverage snapshots

Recoverability behavior:

- If backend restarts, session pipeline attempts restore using stored upload path.
- Rebuilds dataframe and temporary SQLite DB.
- Re-triggers SQL engine/KB build in background.

Viva one-liner:

- We implemented restart-tolerant sessions with lazy state restoration from persisted session metadata.

## 5. Common Viva Questions and Suggested Answers

1. Why use intent routing instead of separate endpoints per feature?
- It keeps conversation natural and allows one chat interface to invoke specialized pipelines dynamically.

2. How did you reduce upload latency?
- We split upload into synchronous preview and asynchronous knowledge-base build with background executors.

3. How do you handle LLM failures in SQL generation?
- We use deterministic aggregate fallback for common KPI queries and return meaningful errors otherwise.

4. How is scalability handled for multiple users?
- SessionManager isolates pipelines per session, and session artifacts are persisted in per-session SQLite files.

5. How does voice maintain reliability?
- It has multiple transcription backends and supports both streaming and upload-based interaction.

6. How do you ensure explainability of AI responses?
- We persist SQL, chart code, insight evidence/confidence, and KPI coverage annotations.

## 6. Demo Script for Viva (2-3 minutes)

1. Start app and create a fresh session.
2. Upload sample dataset.
3. Show session status changing from no data to data loaded.
4. Ask one SQL question.
5. Ask one chart question.
6. Trigger auto insights and show summary + confidence.
7. Use voice input for one query and show transcript.
8. Open session history to prove persistence.

## 7. Key Technical Strengths to Highlight

1. Layered architecture with clean orchestration.
2. Background processing for responsiveness.
3. Parallel insight generation for speed.
4. Multi-provider voice fallback for robustness.
5. Session persistence and restart-aware restoration.
6. Explainability through SQL/code/coverage artifacts.

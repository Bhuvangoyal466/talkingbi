# TalkingBI Technical Implementation Documentation

This version is focused only on:

1. External APIs and provider services used
2. Databases and storage used
3. How each feature is implemented technically

## 1. External APIs and Services Used

### 1.1 LLM Providers

TalkingBI uses provider fallback for generation tasks.

External APIs:

1. Groq Chat Completions API
2. OpenRouter Chat Completions API
3. Ollama local HTTP API (self-hosted, not cloud)

What they are used for:

1. Intent classification from user query
2. SQL generation and refinement
3. Chart type recommendation and extraction fallback
4. Insight generation steps (goal, questions, summary)
5. General conversation fallback

Reliability implementation:

1. Automatic provider order and fallback if one fails
2. Provider-specific model fallback lists
3. Persistent LLM response cache in `data/cache/llm`

### 1.2 Speech-to-Text Providers

External APIs:

1. AssemblyAI REST API
2. Groq Whisper transcription API

Local engine:

1. faster-whisper local model (optional)

Use case:

- Convert recorded audio into transcript text for analytics flow.

Fallback order:

1. Local whisper (if enabled)
2. AssemblyAI (if configured)
3. Groq Whisper

### 1.3 Text-to-Speech

Service/library used:

1. edge-tts

Use case:

- Convert generated BI summary text into spoken MP3 audio.

## 2. Databases and Storage Used

TalkingBI uses multiple stores, each for a specific purpose.

### 2.1 Session SQLite Store

Path:

- `data/sessions/{session_id}.db`

Purpose:

1. Persist message history
2. Persist charts metadata and chart payload
3. Persist insight runs
4. Persist upload metadata

Tables:

1. `messages`
2. `insights`
3. `charts`
4. `uploads`

### 2.2 Temporary SQLite (per upload)

Purpose:

1. SQL execution surface for uploaded dataframe
2. Schema extraction source
3. KB exploration source

Performance tuning used:

1. WAL journal mode
2. Normal synchronous mode
3. Larger page cache

### 2.3 User-Connected Databases

Supported direct connections:

1. SQLite files
2. DuckDB files

Purpose:

- Query existing user DB directly without converting to CSV pipeline.

### 2.4 Vector Database (ChromaDB)

Path:

- `data/chroma`

Purpose:

1. Store SQL triplets as vectors
2. Retrieve semantically similar SQL examples during generation

Stored unit:

- `(schema_fragment, sql_query, nl_description)`

### 2.5 Cache Storage

Paths:

1. `data/cache/llm`
2. `data/cache/whisper`
3. `data/cache/voice`

Purpose:

1. LLM response reuse
2. Whisper model/runtime cache
3. Voice processing artifacts

## 3. Feature Implementation Details

### 3.1 Chat and Intent Routing

Implementation summary:

1. User query enters orchestrator process method.
2. Router classifies intent into SQL, chart, insight, data prep, hybrid, or conversation.
3. Corresponding handler executes feature logic.
4. KPI coverage is attached to response when applicable.
5. Result summary is persisted in session SQLite.

Why it works well:

- Single conversational entrypoint with specialized backend branches.

### 3.2 File Upload and Background Knowledge Build

Implementation summary:

1. Upload endpoint validates file type and stores file.
2. Fast path loads dataframe and returns preview immediately.
3. Background worker builds schema, explores DB, and prepares SQL engine.
4. Frontend can monitor readiness using status flags.

Why this design:

- Keeps upload response fast while heavy indexing runs asynchronously.

### 3.3 SQL Querying

Implementation summary:

1. Schema context is extracted from SQLite/DuckDB source.
2. Vector KB retrieves similar SQL triplets.
3. Dual-agent flow generates and executes SQL iteratively.
4. On repeated failure, deterministic aggregate fallback is attempted for common KPI questions.

Output includes:

1. SQL text
2. Result columns and rows
3. Row count
4. Iteration/fallback metadata

### 3.4 Chart Generation

Implementation summary:

1. Intent is decomposed into x/y/category/aggregation signals.
2. Data extractor builds chart-ready value list from dataframe.
3. Selector recommends best chart type using heuristics plus LLM reasoning.
4. Renderer generates chart via Matplotlib and returns base64 PNG.
5. Structured chart_data is also returned for interactive frontend rendering.

Supported chart families:

1. Bar and horizontal bar
2. Grouped and stacked bar
3. Line and area
4. Scatter
5. Pie
6. Histogram

Frontend behavior:

1. Uses interactive rendering when chart_data is available
2. Falls back to static image otherwise
3. Persists chart history in browser and session DB

### 3.5 Insight Discovery

Implementation summary:

1. Goal is refined from user request.
2. Multiple analytical questions are generated.
3. Discovery runs in parallel threads for lower latency.
4. Results are evaluated and synthesized into executive summary.
5. Insight set is persisted to session store.

Output includes:

1. Insight cards with type and confidence
2. Summary text
3. Goal context

### 3.6 Data Preparation

Implementation summary:

1. User prompt is converted into target schema/transform intent.
2. DeepPrep reasoner executes transformation pipeline.
3. Transformed dataframe replaces active session dataframe.
4. New preview and shape are returned.

### 3.7 Voice Input and Output

Voice input flow:

1. Frontend records audio through MediaRecorder.
2. Audio blob is sent to transcription route.
3. Backend transcribes via fallback chain.
4. Transcript is passed into normal analytics flow.

Voice output flow:

1. Response is summarized into speakable text.
2. Text is clipped to configured max spoken words.
3. edge-tts generates MP3 bytes.
4. Audio is returned to client for playback.

Streaming mode:

1. WebSocket route accepts binary audio frames.
2. Client sends stop control message.
3. Backend transcribes, processes, and emits transcript/result/state events.
4. Optional base64 TTS audio is emitted in same channel.

## 4. DB and API Mapping by Feature

### Chat

1. Uses LLM providers for intent and generation
2. Reads/writes session SQLite

### Upload + SQL

1. Uses temp SQLite for execution
2. Uses ChromaDB for triplet retrieval
3. Uses LLM providers for SQL synthesis

### Charts

1. Uses LLM providers for type/extraction fallback
2. Uses Matplotlib local renderer
3. Stores chart metadata in session SQLite

### Insights

1. Uses LLM providers for multi-step insight pipeline
2. Stores insights in session SQLite

### Voice

1. Uses AssemblyAI or Groq Whisper or local whisper for STT
2. Uses edge-tts for TTS
3. Reuses normal chat analytics pipeline after transcription

## 5. Key Configuration for External APIs and Storage

Provider configuration:

1. `OPENROUTER_API_KEY`
2. `GROQ_API_KEY`
3. `LLM_PROVIDER` and model vars

Voice configuration:

1. `VOICE_USE_LOCAL_TRANSCRIPTION`
2. `WHISPER_MODEL_SIZE`
3. `WHISPER_DEVICE`
4. `TTS_VOICE`
5. `VOICE_MAX_SPOKEN_WORDS`

Storage configuration:

1. `CHROMA_PERSIST_DIR`
2. `UPLOAD_DIR`
3. `CACHE_DIR`

## 6. Practical Notes

1. For lowest latency, keep response cache enabled and tune exploration depth conservatively.
2. For best SQL quality, allow richer KB triplet exploration.
3. For production, add auth, request limits, and metrics around provider fallbacks.

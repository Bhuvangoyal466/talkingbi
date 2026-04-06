import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.config import settings
from core.logger import logger
from core.llm_client import llm
from orchestrator.session_manager import session_manager
from api.routes import chat, data, charts, insights, voice


# ── Fix 4: embedding model warmup ─────────────────────────────────────────────
# sentence-transformers loads the model on the first call, which adds 3-5 s
# of cold-start latency to whatever request happens to arrive first.
# The lifespan hook runs once at startup and pre-loads the model into memory
# so every subsequent embed() call is instant.
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Warming up embedding model...")
    try:
        from vector_store.embedder import embedder
        embedder.embed("warmup")
        logger.info("Embedding model ready.")
    except Exception as e:
        # Warmup failure is non-fatal — the model will still lazy-load on first use
        logger.warning(f"Embedding warmup failed (will lazy-load): {e}")
    yield


app = FastAPI(
    title="TalkingBI API",
    version="1.0.0",
    description="Conversational Business Intelligence powered by LLMs",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,   # Fix 4 — replaces the old @app.on_event("startup") pattern
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount route groups
app.include_router(chat.router)
app.include_router(data.router)
app.include_router(charts.router)
app.include_router(insights.router)
app.include_router(voice.router)


@app.get("/", tags=["health"])
async def root():
    return {
        "name": "TalkingBI API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy", "active_sessions": session_manager.session_count()}


@app.post("/session/new", tags=["session"])
async def new_session():
    """Create a new conversation session."""
    session_id = session_manager.create()
    return {"session_id": session_id}


@app.get("/session/{session_id}/status", tags=["session"])
async def session_status(session_id: str):
    """
    Get current status of a session.

    Fix 1 — exposes kb_ready so the frontend can show a 'building KB...'
    spinner instead of letting the user hit a confusing 'no DB' error.
    """
    pipeline = session_manager.get(session_id)
    return {
        "session_id": session_id,
        "has_db": pipeline.db_schema is not None,
        "has_data": pipeline.current_df is not None,
        "kb_ready": pipeline._kb_ready,           # Fix 1 — new field
        "message_count": len(pipeline.session_history),
        "db_name": pipeline.db_schema.db_name if pipeline.db_schema else None,
        "data_shape": list(pipeline.current_df.shape) if pipeline.current_df is not None else None,
    }


@app.delete("/session/{session_id}", tags=["session"])
async def delete_session(session_id: str):
    """Delete a session and free its resources."""
    deleted = session_manager.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@app.get("/session/{session_id}/history", tags=["session"])
async def session_history(session_id: str, limit: int = 100):
    """Return chat messages stored in the session's SQLite history DB."""
    pipeline = session_manager.get(session_id)
    return {"messages": pipeline.store.get_messages(limit=limit)}


@app.get("/session/{session_id}/insights", tags=["session"])
async def session_insights(session_id: str, limit: int = 100):
    """Return all insights discovered in this session."""
    pipeline = session_manager.get(session_id)
    return {"insights": pipeline.store.get_insights(limit=limit)}


@app.get("/session/{session_id}/charts", tags=["session"])
async def session_charts(session_id: str, limit: int = 50):
    """Return chart metadata recorded in this session."""
    pipeline = session_manager.get(session_id)
    return {"charts": pipeline.store.get_charts(limit=limit)}


@app.get("/session/{session_id}/store-summary", tags=["session"])
async def session_store_summary(session_id: str):
    """Return a summary of what's stored in the session SQLite DB."""
    pipeline = session_manager.get(session_id)
    return pipeline.store.summary()


@app.get("/session/{session_id}/chart-suggestions", tags=["session"])
async def chart_suggestions(session_id: str):
    """
    Return data-aware suggested chart prompts and applicable chart types
    based on the column names and dtypes of the loaded DataFrame.
    """
    pipeline = session_manager.get(session_id)
    df = pipeline.current_df
    if df is None:
        return {"suggestions": [], "chart_types": []}

    cols = list(df.columns)
    dtypes = dict(df.dtypes.astype(str))

    numeric_cols = [c for c, t in dtypes.items() if "int" in t or "float" in t]
    date_cols = [c for c, t in dtypes.items() if "datetime" in t or "date" in t]
    cat_cols = [c for c in cols if c not in numeric_cols and c not in date_cols]

    # Determine which chart types are applicable given the data shape
    chart_types: list[dict] = []
    if numeric_cols:
        chart_types.append({"type": "bar", "label": "Bar Chart", "desc": "Compare values across categories"})
        chart_types.append({"type": "horizontal_bar", "label": "Horizontal Bar", "desc": "Best for long category labels"})
        chart_types.append({"type": "histogram", "label": "Histogram", "desc": "Distribution of a numeric field"})
    if numeric_cols and (date_cols or cat_cols):
        chart_types.append({"type": "line", "label": "Line Chart", "desc": "Trend over time or ordered series"})
        chart_types.append({"type": "area", "label": "Area Chart", "desc": "Cumulative trend visualization"})
    if numeric_cols and cat_cols:
        chart_types.append({"type": "pie", "label": "Pie Chart", "desc": "Part-to-whole for a category"})
        chart_types.append({"type": "scatter", "label": "Scatter Plot", "desc": "Correlation between two numeric fields"})
    if len(cat_cols) >= 1 and numeric_cols:
        chart_types.append({"type": "grouped_bar", "label": "Grouped Bar", "desc": "Compare sub-groups side by side"})
        chart_types.append({"type": "stacked_bar", "label": "Stacked Bar", "desc": "Show composition within groups"})

    # Build suggested prompts using actual column names via LLM
    from core.llm_client import llm
    prompt = f"""You are a data analyst assistant. Given the column names and types below,
generate exactly 6 short, natural-language chart prompt suggestions a user could ask.

Columns: {cols}
Numeric: {numeric_cols}
Date/time: {date_cols}
Categorical: {cat_cols}

Rules:
- Use real column names from the list above
- Each suggestion should be ≤12 words
- Cover different chart types (bar, line, pie, scatter, histogram)
- Mention the chart type naturally (e.g. "as a pie chart", "bar chart of", "distribution of")
- Return valid JSON: {{"suggestions": ["...", "...", "...", "...", "...", "..."]}}"""

    try:
        import json
        raw = llm.chat(prompt, json_mode=True, temperature=0.3, use_cache=True)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        suggestions = json.loads(cleaned).get("suggestions", [])[:6]
    except Exception:
        # Fallback: build basic suggestions from column names
        suggestions = []
        if numeric_cols and cat_cols:
            suggestions.append(f"Bar chart of {numeric_cols[0]} by {cat_cols[0]}")
            suggestions.append(f"Pie chart of {numeric_cols[0]} by {cat_cols[0]}")
        if numeric_cols and date_cols:
            suggestions.append(f"Line chart of {numeric_cols[0]} over {date_cols[0]}")
        if len(numeric_cols) >= 2:
            suggestions.append(f"Scatter plot of {numeric_cols[0]} vs {numeric_cols[1]}")
        if numeric_cols:
            suggestions.append(f"Distribution of {numeric_cols[0]} as histogram")
        if cat_cols and len(cat_cols) > 1 and numeric_cols:
            suggestions.append(f"Grouped bar of {numeric_cols[0]} by {cat_cols[0]} and {cat_cols[1]}")

    return {"suggestions": suggestions, "chart_types": chart_types}


@app.get("/sessions/history", tags=["session"])
async def list_past_sessions():
    """List all saved session history DBs with their summaries (skips empty sessions)."""
    from core.session_store import SessionStore
    sessions_dir = Path("data/sessions")
    if not sessions_dir.exists():
        return {"sessions": []}
    results = []
    for db_file in sorted(sessions_dir.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True):
        sid = db_file.stem
        try:
            store = SessionStore(sid)
            summary = store.summary()
            if (
                summary["messages"] == 0
                and summary["insights"] == 0
                and summary["charts"] == 0
                and summary["uploads"] == 0
            ):
                store.close()
                continue
            msgs = store.get_messages(limit=2)
            preview = next((m["content"][:80] for m in msgs if m["role"] == "user"), "")
            summary["preview"] = preview
            summary["modified"] = db_file.stat().st_mtime
            store.close()
            results.append(summary)
        except Exception:
            pass
    return {"sessions": results}


@app.delete("/sessions/history/{session_id}", tags=["session"])
async def delete_past_session(session_id: str):
    """Permanently delete a past session's SQLite history file."""
    db_file = Path("data/sessions") / f"{session_id}.db"
    if not db_file.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        # Close the pipeline's open SQLite connection before unlinking.
        # On Windows an open file handle prevents deletion (PermissionError).
        pipeline = session_manager._sessions.get(session_id)
        if pipeline is not None and hasattr(pipeline, "store"):
            pipeline.store.close()
        session_manager.delete(session_id)
        db_file.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not delete session: {e}")
    return {"status": "deleted", "session_id": session_id}


_ALLOWED_PROVIDERS = ("openrouter", "groq", "ollama")


class ProviderPayload(BaseModel):
    provider: str


@app.get("/llm/provider", tags=["llm"])
async def get_llm_provider():
    """Return the currently active LLM provider."""
    return {"provider": llm.provider, "available": list(_ALLOWED_PROVIDERS)}


@app.post("/llm/provider", tags=["llm"])
async def set_llm_provider(payload: ProviderPayload):
    """Switch the active LLM provider for all subsequent requests."""
    if payload.provider not in _ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"provider must be one of {_ALLOWED_PROVIDERS}",
        )
    llm.set_provider(payload.provider)
    return {"provider": llm.provider}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
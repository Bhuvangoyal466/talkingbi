import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from core.config import settings
from core.logger import logger
from core.llm_client import llm
from orchestrator.session_manager import session_manager
from api.routes import chat, data, charts, insights

app = FastAPI(
    title="TalkingBI API",
    version="1.0.0",
    description="Conversational Business Intelligence powered by LLMs",
    docs_url="/docs",
    redoc_url="/redoc",
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
    """Get current status of a session."""
    pipeline = session_manager.get(session_id)
    return {
        "session_id": session_id,
        "has_db": pipeline.db_schema is not None,
        "has_data": pipeline.current_df is not None,
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
        raise HTTPException(status_code=400, detail=f"provider must be one of {_ALLOWED_PROVIDERS}")
    llm.set_provider(payload.provider)
    return {"provider": llm.provider}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)

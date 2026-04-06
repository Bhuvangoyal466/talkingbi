from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from api.schemas.request import ChatRequest
from orchestrator.session_manager import session_manager
from core.logger import logger

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(req: ChatRequest):
    """Process a chat message and return the pipeline result."""
    try:
        pipeline = session_manager.get(req.session_id)
        result = pipeline.process(req.message)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

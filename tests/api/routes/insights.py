from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from api.schemas.request import ChatRequest
from orchestrator.session_manager import session_manager
from core.logger import logger

router = APIRouter(prefix="/insights", tags=["insights"])


@router.post("/discover")
async def discover_insights(req: ChatRequest):
    """Discover insights from current data using a goal statement."""
    pipeline = session_manager.get(req.session_id)
    if pipeline.current_df is None:
        raise HTTPException(
            status_code=400,
            detail="No data available. Upload a file or run a SQL query first.",
        )
    try:
        result = pipeline._handle_insight(req.message)
        if result.get("type") == "error":
            raise HTTPException(status_code=422, detail=result["error"])
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Insight discovery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

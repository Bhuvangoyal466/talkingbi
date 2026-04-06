from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from api.schemas.request import ChatRequest
from orchestrator.session_manager import session_manager
from core.logger import logger

router = APIRouter(prefix="/charts", tags=["charts"])


@router.post("/generate")
async def generate_chart(req: ChatRequest):
    """Generate a chart from a natural language description."""
    pipeline = session_manager.get(req.session_id)
    if pipeline.current_df is None and pipeline.sql_engine is None:
        raise HTTPException(
            status_code=400,
            detail="No data available. Upload a file or connect a database first.",
        )
    try:
        result = pipeline._handle_chart(req.message, chart_type_override=req.chart_type)
        if result.get("type") == "error":
            raise HTTPException(status_code=422, detail=result["error"])
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
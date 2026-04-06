import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from api.schemas.request import DBConnectRequest
from orchestrator.session_manager import session_manager
from core.config import settings
from core.logger import logger
from core.exceptions import DatabaseConnectionError, FileLoadError

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Query(default="default"),
):
    """Upload a CSV/Excel/Parquet file for analysis."""
    allowed_types = {".csv", ".xlsx", ".xls", ".parquet"}
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {allowed_types}",
        )

    upload_path = Path(settings.UPLOAD_DIR) / file.filename

    try:
        with open(upload_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {e}")

    pipeline = session_manager.get(session_id)
    try:
        result = pipeline.load_file(str(upload_path))
        return JSONResponse(content=result)
    except FileLoadError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"File load error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect-db")
async def connect_db(req: DBConnectRequest):
    """Connect a SQLite/DuckDB database for querying."""
    if not Path(req.db_path).exists():
        raise HTTPException(status_code=404, detail=f"Database file not found: {req.db_path}")

    pipeline = session_manager.get(req.session_id)
    try:
        result = pipeline.connect_database(req.db_path)
        return JSONResponse(content=result)
    except DatabaseConnectionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"DB connect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview")
async def preview_data(session_id: str = Query(default="default"), rows: int = 10):
    """Preview the current working DataFrame."""
    pipeline = session_manager.get(session_id)
    if pipeline.current_df is None:
        raise HTTPException(status_code=404, detail="No data loaded in this session.")
    df = pipeline.current_df
    return JSONResponse(
        content={
            "rows": len(df),
            "columns": list(df.columns),
            "dtypes": dict(df.dtypes.astype(str)),
            "preview": df.head(rows).to_dict(orient="records"),
        }
    )

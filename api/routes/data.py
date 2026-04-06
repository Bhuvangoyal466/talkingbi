import asyncio
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse

from api.schemas.request import DBConnectRequest
from orchestrator.session_manager import session_manager
from core.config import settings
from core.logger import logger
from core.exceptions import DatabaseConnectionError, FileLoadError

router = APIRouter(prefix="/data", tags=["data"])

# Fix 1 — Shared executor for background KB builds.
# max_workers=2: allows two concurrent uploads without flooding the LLM API.
# Each worker runs _build_sql_engine_bg which is CPU-light but LLM-heavy,
# so 2 workers are enough to keep the API busy without overwhelming free-tier
# rate limits.
_bg_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kb-build")


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Query(default="default"),
):
    """
    Upload a CSV/Excel/Parquet file for analysis.

    Fix 1 — Two-phase response:
      Phase 1 (synchronous, < 1 s): save file, pandas read, write temp SQLite.
                                     Returns immediately with a preview.
      Phase 2 (background thread):  SchemaRepresentation + DatabaseExplorer
                                     MCTS build + ChromaDB persist.
                                     User can start asking questions once
                                     kb_status changes to "ready" (poll
                                     /session/{id}/status or just wait ~15-40s).
    """
    allowed_types = {".csv", ".xlsx", ".xls", ".parquet"}
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {sorted(allowed_types)}",
        )

    upload_path = Path(settings.UPLOAD_DIR) / file.filename

    try:
        with open(upload_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {e}")

    pipeline = session_manager.get(session_id)
    try:
        # Phase 1 — fast: pandas read + temp SQLite write (Fix 5 WAL is inside here)
        result = pipeline.load_file(str(upload_path))
    except FileLoadError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"File load error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Phase 2 — Fix 1: schedule KB build on the background executor.
    # run_in_executor is non-blocking; the current request returns while
    # _build_sql_engine_bg runs on the thread pool.
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _bg_executor,
        pipeline._build_sql_engine_bg,
        str(upload_path),
    )

    # result already contains kb_status: "building_in_background" from load_file
    return JSONResponse(content=result)


@router.post("/connect-db")
async def connect_db(req: DBConnectRequest):
    """Connect a SQLite/DuckDB database for querying."""
    raw = req.db_path.strip()
    candidates = [
        Path(raw),
        Path.cwd() / raw.lstrip("/\\"),
        Path(settings.UPLOAD_DIR) / Path(raw).name,
        Path("data") / Path(raw).name,
    ]
    resolved = next((p for p in candidates if p.exists()), None)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Database file not found: {raw!r}. "
                "Tip: enter a full path like D:\\talkingbi\\data\\business.db, "
                "or upload the .db file directly."
            ),
        )
    req = DBConnectRequest(db_path=str(resolved), session_id=req.session_id)

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
            # Fix 1 — expose KB readiness so the frontend can show a spinner
            "kb_ready": pipeline._kb_ready,
        }
    )
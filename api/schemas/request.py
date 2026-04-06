from pydantic import BaseModel
from typing import Optional, Any


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    chart_type: Optional[str] = None  # explicit override sent from the dropdown


class DBConnectRequest(BaseModel):
    db_path: str
    session_id: str = "default"


class SessionRequest(BaseModel):
    session_id: str


class UploadResponse(BaseModel):
    status: str
    rows: int
    columns: list
    dtypes: dict
    preview: list


class ChatResponse(BaseModel):
    type: str
    session_id: str
    result: Any


class SessionStatusResponse(BaseModel):
    session_id: str
    has_db: bool
    has_data: bool
    message_count: int
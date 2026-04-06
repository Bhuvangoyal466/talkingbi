from pydantic import BaseModel
from typing import Any, Optional


class BaseResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None


class SQLResultResponse(BaseResponse):
    sql: str = ""
    columns: list = []
    rows: list = []
    rows_returned: int = 0


class ChartResponse(BaseResponse):
    image_base64: str = ""
    chart_type: str = ""
    title: str = ""
    data_points: int = 0
    code: str = ""
    chart_data: dict = {}


class InsightResponse(BaseResponse):
    goal: str = ""
    insights: list = []
    summary: str = ""
    total_insights: int = 0


class DataPrepResponse(BaseResponse):
    pipeline: list = []
    shape: list = []
    columns: list = []
    preview: list = []


class ConversationResponse(BaseResponse):
    response: str = ""


class VoiceTranscriptionResponse(BaseResponse):
    transcript: str = ""


class VoiceAnalysisResponse(BaseResponse):
    transcript: str = ""
    answer: str = ""
    relevant_kpis: list = []
    confidence: float = 0.0
    session_id: str = "default"
    result_type: str = "conversation"

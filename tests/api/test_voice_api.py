"""API tests for voice POST endpoints."""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Support direct execution: `python tests/api/test_voice_api.py`
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.routes import voice


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(voice.router)
    return TestClient(app)


def test_transcribe_only_success(monkeypatch):
    async def fake_transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
        assert audio_bytes
        assert filename == "sample.webm"
        return "hello from audio"

    monkeypatch.setattr(voice, "transcribe_audio", fake_transcribe_audio)

    client = _build_client()
    response = client.post(
        "/voice/transcribe-only",
        files={"audio": ("sample.webm", b"fake-audio", "audio/webm")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["transcript"] == "hello from audio"


def test_analyse_success(monkeypatch):
    async def fake_transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
        assert audio_bytes
        return "what is my revenue"

    async def fake_analyse_voice_query(
        transcript: str,
        dashboard_context: str = "",
        kpis=None,
        session_id: str = "default",
    ) -> dict:
        assert transcript == "what is my revenue"
        assert dashboard_context == "Revenue: 100000"
        assert kpis == ["Revenue", "Profit"]
        assert session_id == "session-123"
        return {
            "transcript": transcript,
            "answer": "Revenue is 100000",
            "relevant_kpis": ["Revenue"],
            "confidence": 0.91,
            "session_id": session_id,
            "result_type": "conversation",
            "result": {"type": "conversation", "response": "Revenue is 100000"},
        }

    monkeypatch.setattr(voice, "transcribe_audio", fake_transcribe_audio)
    monkeypatch.setattr(voice, "analyse_voice_query", fake_analyse_voice_query)

    client = _build_client()
    response = client.post(
        "/voice/analyse",
        files={"audio": ("sample.webm", b"fake-audio", "audio/webm")},
        data={
            "dashboard_context": "Revenue: 100000",
            "kpis": "Revenue, Profit",
            "session_id": "session-123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["transcript"] == "what is my revenue"
    assert body["answer"] == "Revenue is 100000"
    assert body["relevant_kpis"] == ["Revenue"]
    assert body["session_id"] == "session-123"
    assert body["result_type"] == "conversation"


def test_respond_success(monkeypatch):
    async def fake_analyse_voice_query(
        transcript: str,
        dashboard_context: str = "",
        kpis=None,
        session_id: str = "default",
    ) -> dict:
        return {
            "transcript": transcript,
            "answer": "Processed",
            "relevant_kpis": ["Revenue"],
            "confidence": 0.74,
            "session_id": session_id,
            "result_type": "conversation",
            "result": {"type": "conversation", "response": "Processed"},
        }

    monkeypatch.setattr(voice, "analyse_voice_query", fake_analyse_voice_query)

    client = _build_client()
    response = client.post(
        "/voice/respond",
        data={
            "transcript": "show my revenue trend",
            "dashboard_context": "Revenue by month",
            "kpis": "Revenue",
            "session_id": "session-abc",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "show my revenue trend"
    assert body["answer"] == "Processed"
    assert body["session_id"] == "session-abc"


def test_analyse_returns_500_on_service_failure(monkeypatch):
    async def fake_transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
        raise RuntimeError("transcription failed")

    monkeypatch.setattr(voice, "transcribe_audio", fake_transcribe_audio)

    client = _build_client()
    response = client.post(
        "/voice/analyse",
        files={"audio": ("sample.webm", b"fake-audio", "audio/webm")},
        data={"session_id": "session-123"},
    )

    assert response.status_code == 500
    assert "transcription failed" in response.json()["detail"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))

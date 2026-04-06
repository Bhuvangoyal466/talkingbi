import asyncio
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import requests
from groq import AsyncGroq

try:
    from faster_whisper import WhisperModel as _WhisperModel  # type: ignore[import-not-found]

    _LOCAL_WHISPER_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _WhisperModel = None  # type: ignore[assignment]
    _LOCAL_WHISPER_AVAILABLE = False

try:
    import edge_tts  # type: ignore[import-not-found]

    _EDGE_TTS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    edge_tts = None  # type: ignore[assignment]
    _EDGE_TTS_AVAILABLE = False

from core.config import settings
from core.llm_client import llm
from core.logger import logger
from orchestrator.session_manager import session_manager

_ASSEMBLY_BASE_URL = "https://api.assemblyai.com"
_ASSEMBLY_POLL_INTERVAL_SECONDS = 3
_ASSEMBLY_MAX_POLLS = 80


@lru_cache(maxsize=1)
def _get_local_whisper_model() -> Any:
    if not _LOCAL_WHISPER_AVAILABLE:
        raise RuntimeError("Local Whisper is not installed")

    return _WhisperModel(
        settings.WHISPER_MODEL_SIZE,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
        download_root="./data/cache/whisper",
    )


def _clean_transcript_text(text: str) -> str:
    normalized = " ".join(text.split())
    for marker in ("[MUSIC]", "[APPLAUSE]", "(silence)"):
        normalized = normalized.replace(marker, "")
    return " ".join(normalized.split()).strip()


def _is_no_spoken_audio_error(message: str) -> bool:
    normalized = message.lower()
    return (
        "no spoken audio" in normalized
        or "language_detection cannot be performed" in normalized
        or "no speech" in normalized
        or "empty transcript" in normalized
    )


def _extract_text_from_groq_response(response: object) -> str:
    if hasattr(response, "text"):
        return (getattr(response, "text") or "").strip()
    if isinstance(response, dict):
        return str(response.get("text", "")).strip()
    return ""


def _pick_relevant_kpis(transcript: str, kpis: Optional[list]) -> list:
    if not kpis:
        return []
    text = transcript.lower()
    return [k for k in kpis if k and str(k).lower() in text]


def _make_voice_answer(result: dict) -> str:
    if not isinstance(result, dict):
        return str(result)

    kpi_summary = ""
    if isinstance(result.get("kpi_coverage"), dict):
        kpi_summary = result["kpi_coverage"].get("summary", "") or ""

    for key in ("answer", "response", "summary", "error"):
        value = result.get(key)
        if value:
            text = str(value)
            if kpi_summary and kpi_summary not in text:
                return f"{text} {kpi_summary}".strip()
            return text

    if result.get("type") in ("sql", "sql_result"):
        rows = result.get("rows_returned", 0)
        return f"I ran the query and got {rows} rows."

    if result.get("type") == "chart":
        title = result.get("title") or result.get("chart_type") or "chart"
        return f"I generated a {title} for you."

    if result.get("type") == "insights":
        total = len(result.get("insights", []))
        answer = f"I found {total} insights from your data."
        if kpi_summary:
            return f"{answer} {kpi_summary}".strip()
        return answer

    answer = "I processed your request."
    if kpi_summary:
        return f"{answer} {kpi_summary}".strip()
    return answer


def build_voice_summary(result: dict) -> str:
    """Return a concise speakable summary for a BI response."""
    summary = _make_voice_answer(result)
    words = summary.split()
    if len(words) <= settings.VOICE_MAX_SPOKEN_WORDS:
        return summary

    clipped = " ".join(words[: settings.VOICE_MAX_SPOKEN_WORDS])
    last_sentence = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
    if last_sentence > len(clipped) * 0.7:
        return clipped[: last_sentence + 1]
    return clipped.rstrip() + " ..."


async def synthesize_voice_audio(text: str) -> tuple[bytes | None, str]:
    """Synthesize a spoken MP3 response when edge-tts is installed."""
    spoken = text.strip()
    if not spoken or not _EDGE_TTS_AVAILABLE:
        return None, ""

    communicate = edge_tts.Communicate(
        text=spoken,
        voice=settings.TTS_VOICE,
        rate=settings.TTS_RATE,
        pitch=settings.TTS_PITCH,
    )

    audio_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            audio_chunks.append(chunk["data"])

    return b"".join(audio_chunks), "audio/mpeg"


def _confidence_score(result: dict, relevant_kpis: list) -> float:
    base = 0.74 if relevant_kpis else 0.62

    if result.get("type") == "error":
        base -= 0.2

    answer = _make_voice_answer(result)
    if not answer or answer.strip().lower().startswith("i'm here to help"):
        base -= 0.09

    return max(0.0, min(0.99, round(base, 2)))


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    if not audio_bytes:
        raise RuntimeError("Empty audio file uploaded")

    suffix = Path(filename or "audio.webm").suffix or ".webm"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="tbi_voice_")
    os.close(fd)

    try:
        with open(tmp_path, "wb") as f:
            f.write(audio_bytes)

        if settings.VOICE_USE_LOCAL_TRANSCRIPTION and _LOCAL_WHISPER_AVAILABLE:
            try:
                model = _get_local_whisper_model()
                segments, _ = model.transcribe(
                    tmp_path,
                    language="en",
                    initial_prompt=settings.WHISPER_INITIAL_PROMPT,
                    beam_size=5,
                    vad_filter=False,
                    temperature=0.0,
                    condition_on_previous_text=False,
                )
                text = _clean_transcript_text(
                    " ".join(segment.text.strip() for segment in segments)
                )
                if text:
                    return text
                raise RuntimeError("Local Whisper returned an empty transcript")
            except Exception as e:
                logger.warning(
                    f"Local Whisper transcription failed, falling back to hosted provider: {e}"
                )

        if settings.ASSEMBLYAI_API_KEY:
            try:
                text = await asyncio.to_thread(
                    _assemblyai_transcribe_via_rest,
                    audio_bytes,
                    filename or f"audio{suffix}",
                )
                if text:
                    return _clean_transcript_text(text)
            except Exception as e:
                if _is_no_spoken_audio_error(str(e)):
                    raise RuntimeError(
                        "No spoken audio was detected. Please record a clear voice query and try again."
                    ) from e
                logger.warning(
                    f"AssemblyAI transcription failed. Falling back to Groq Whisper: {e}"
                )

        if settings.GROQ_API_KEY:
            with open(tmp_path, "rb") as f:
                audio_content = f.read()

            groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            groq_resp = await groq_client.audio.transcriptions.create(
                file=(filename or f"audio{suffix}", audio_content),
                model="whisper-large-v3-turbo",
                response_format="json",
                language="en",
                temperature=0,
            )
            text = _extract_text_from_groq_response(groq_resp)
            if text:
                return _clean_transcript_text(text)

            raise RuntimeError("Groq Whisper returned an empty transcript")

        raise RuntimeError(
            "Speech transcription is not configured. Set ASSEMBLYAI_API_KEY or GROQ_API_KEY."
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _assemblyai_transcribe_via_rest(audio_bytes: bytes, filename: str) -> str:
    headers = {
        "authorization": settings.ASSEMBLYAI_API_KEY,
    }

    upload_resp = requests.post(
        f"{_ASSEMBLY_BASE_URL}/v2/upload",
        headers=headers,
        data=audio_bytes,
        timeout=120,
    )
    upload_resp.raise_for_status()
    upload_url = upload_resp.json().get("upload_url")
    if not upload_url:
        raise RuntimeError("AssemblyAI upload failed: missing upload_url")

    transcript_payload = {
        "audio_url": upload_url,
        "language_detection": True,
        "speech_models": ["universal-3-pro", "universal-2"],
    }
    create_resp = requests.post(
        f"{_ASSEMBLY_BASE_URL}/v2/transcript",
        headers=headers,
        json=transcript_payload,
        timeout=120,
    )
    create_resp.raise_for_status()
    transcript_id = create_resp.json().get("id")
    if not transcript_id:
        raise RuntimeError("AssemblyAI transcript creation failed: missing id")

    polling_endpoint = f"{_ASSEMBLY_BASE_URL}/v2/transcript/{transcript_id}"
    for _ in range(_ASSEMBLY_MAX_POLLS):
        poll_resp = requests.get(polling_endpoint, headers=headers, timeout=60)
        poll_resp.raise_for_status()
        result = poll_resp.json()
        status = result.get("status")

        if status == "completed":
            text = (result.get("text") or "").strip()
            if not text:
                raise RuntimeError("AssemblyAI returned empty transcript")
            return text

        if status == "error":
            error_text = str(result.get("error", "unknown error"))
            if _is_no_spoken_audio_error(error_text):
                raise RuntimeError(
                    "No spoken audio was detected. Please record a clear voice query and try again."
                )
            raise RuntimeError(f"Transcription failed: {error_text}")

        import time

        time.sleep(_ASSEMBLY_POLL_INTERVAL_SECONDS)

    raise RuntimeError("AssemblyAI transcription timed out while polling")


async def analyse_voice_query(
    transcript: str,
    dashboard_context: str = "",
    kpis: Optional[list] = None,
    session_id: str = "default",
) -> dict:
    pipeline = session_manager.get(session_id)

    # Keep stateful conversation for back-and-forth turns.
    result = await asyncio.to_thread(pipeline.process, transcript)

    # If user passed explicit context/KPIs and we are in generic conversation mode,
    # enrich the response with a direct grounded answer.
    if result.get("type") == "conversation" and (dashboard_context or kpis):
        prompt = f"""You are a voice BI assistant.
User transcript: {transcript}
Dashboard context: {dashboard_context or 'Not provided'}
KPIs: {kpis or []}

Give a concise answer grounded in the provided context.
If the context is insufficient, state what is missing in one sentence."""
        try:
            enriched = llm.chat(prompt, temperature=0.2, use_cache=False)
            result = {
                "type": "conversation",
                "response": enriched,
            }
        except Exception as e:
            logger.warning(f"Voice enrichment prompt failed: {e}")

    relevant = _pick_relevant_kpis(transcript, kpis)
    answer = _make_voice_answer(result)
    confidence = _confidence_score(result, relevant)

    return {
        "transcript": transcript,
        "answer": answer,
        "relevant_kpis": relevant,
        "confidence": confidence,
        "session_id": session_id,
        "result_type": result.get("type", "conversation"),
        "result": result,
    }

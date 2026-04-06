import asyncio
import base64
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from api.schemas.response import VoiceAnalysisResponse, VoiceTranscriptionResponse
from core.logger import logger
from core.voice_service import analyse_voice_query, build_voice_summary, synthesize_voice_audio, transcribe_audio
from orchestrator.session_manager import session_manager

router = APIRouter(prefix="/voice", tags=["voice"])


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket, session_id: str = "default"):
    await websocket.accept()
    await websocket.send_json({"type": "state", "state": "idle"})

    audio_buffer = bytearray()
    recording_started = False

    try:
        while True:
            message = await websocket.receive()

            if message.get("bytes") is not None:
                if not recording_started:
                    recording_started = True
                    await websocket.send_json({"type": "state", "state": "listening"})
                audio_buffer.extend(message["bytes"])
                continue

            text = message.get("text")
            if not text:
                continue

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid voice control message"})
                continue

            if payload.get("type") != "stop":
                continue

            await websocket.send_json({"type": "state", "state": "transcribing"})
            audio_bytes = bytes(audio_buffer)
            audio_buffer.clear()
            recording_started = False

            if not audio_bytes:
                await websocket.send_json({"type": "error", "message": "No audio captured"})
                await websocket.send_json({"type": "state", "state": "idle"})
                continue

            transcript = await transcribe_audio(audio_bytes, payload.get("filename", "voice.webm"))
            if not transcript.strip():
                await websocket.send_json({"type": "error", "message": "No spoken audio was detected"})
                await websocket.send_json({"type": "state", "state": "idle"})
                continue

            await websocket.send_json({"type": "transcript", "text": transcript, "final": True})
            await websocket.send_json({"type": "state", "state": "processing"})

            pipeline = session_manager.get(session_id)
            result = await asyncio.to_thread(pipeline.process, transcript)

            await websocket.send_json({"type": "response", "data": result})

            speak_text = build_voice_summary(result)
            await websocket.send_json({"type": "speech", "text": speak_text})

            audio_data, mime_type = await synthesize_voice_audio(speak_text)
            if audio_data:
                await websocket.send_json(
                    {
                        "type": "audio",
                        "mime": mime_type or "audio/mpeg",
                        "data": base64.b64encode(audio_data).decode("ascii"),
                    }
                )

            await websocket.send_json({"type": "tts_complete"})
            await websocket.send_json({"type": "state", "state": "idle"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Voice stream failed: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/transcribe-only", response_model=VoiceTranscriptionResponse)
async def transcribe_only(audio: UploadFile = File(...)):
    try:
        audio_bytes = await audio.read()
        transcript = await transcribe_audio(audio_bytes, audio.filename or "audio.webm")
        return VoiceTranscriptionResponse(transcript=transcript)
    except Exception as e:
        logger.error(f"Voice transcribe-only failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyse", response_model=VoiceAnalysisResponse)
async def analyse_voice(
    audio: UploadFile = File(...),
    dashboard_context: str = Form(""),
    kpis: str = Form(""),
    session_id: str = Form("default"),
):
    try:
        audio_bytes = await audio.read()
        transcript = await transcribe_audio(audio_bytes, audio.filename or "audio.webm")
        kpi_list = [k.strip() for k in kpis.split(",") if k.strip()]

        result = await analyse_voice_query(
            transcript=transcript,
            dashboard_context=dashboard_context,
            kpis=kpi_list,
            session_id=session_id,
        )

        return VoiceAnalysisResponse(
            transcript=result["transcript"],
            answer=result["answer"],
            relevant_kpis=result["relevant_kpis"],
            confidence=result["confidence"],
            session_id=result["session_id"],
            result_type=result["result_type"],
        )
    except Exception as e:
        logger.error(f"Voice analyse failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/respond")
async def respond_from_transcript(
    transcript: str = Form(...),
    dashboard_context: str = Form(""),
    kpis: str = Form(""),
    session_id: str = Form("default"),
):
    """Generate the next voice-agent reply from an already transcribed utterance."""
    try:
        kpi_list = [k.strip() for k in kpis.split(",") if k.strip()]
        result = await analyse_voice_query(
            transcript=transcript,
            dashboard_context=dashboard_context,
            kpis=kpi_list,
            session_id=session_id,
        )
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Voice respond failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

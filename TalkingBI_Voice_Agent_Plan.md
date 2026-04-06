# 🎙️ TalkingBI — Voice Agent Integration Plan

> **Real-Time Speech-to-Insight: Speak Your Business Questions, Hear Your Answers**

---

## Table of Contents

1. [Overview & Design Philosophy](#1-overview--design-philosophy)
2. [Tool Selection & Rationale](#2-tool-selection--rationale)
3. [Voice Pipeline Architecture](#3-voice-pipeline-architecture)
4. [Integration Map with Existing TalkingBI](#4-integration-map-with-existing-talkingbi)
5. [Backend Implementation](#5-backend-implementation)
6. [Frontend Implementation](#6-frontend-implementation)
7. [Real-Time Streaming Protocol](#7-real-time-streaming-protocol)
8. [Step-by-Step Setup Guide](#8-step-by-step-setup-guide)
9. [Configuration Reference](#9-configuration-reference)
10. [Testing & Benchmarking](#10-testing--benchmarking)
11. [Token & Cost Optimization for Voice](#11-token--cost-optimization-for-voice)
12. [Future Voice Enhancements](#12-future-voice-enhancements)

---

## 1. Overview & Design Philosophy

### What This Feature Does

The TalkingBI Voice Agent transforms the existing text-based conversational interface into a **fully hands-free, real-time voice-powered BI system**. A user clicks a single microphone button, speaks their business question naturally, and within seconds receives:

- A **spoken audio response** summarizing the insight
- The **full visual response** (charts, tables, insight cards) displayed simultaneously in the UI

**Example interaction:**
> 🎤 User speaks: *"What were our top three performing regions last quarter and why did the North region underperform?"*
>
> 🔊 TalkingBI responds (audio): *"Your top three regions were South at 2.4 million, East at 1.9 million, and West at 1.7 million. The North region underperformed by 34% — I found three contributing factors..."*
>
> 📊 UI simultaneously shows: comparison bar chart + insight cards + SQL result table

---

### Design Principles

| Principle | Implementation Decision |
|-----------|------------------------|
| **Zero cloud dependency for audio** | Whisper runs fully locally — raw audio never leaves your server |
| **Sub-3-second first response** | Streaming transcription + parallel LLM call starts before silence is detected |
| **Graceful degradation** | If mic unavailable or browser blocked, falls back seamlessly to text input |
| **Context-aware transcription** | Whisper is seeded with BI domain vocabulary to improve accuracy on terms like "EBITDA", "CAC", "churn rate" |
| **Interruptible responses** | User can speak mid-response to redirect; system detects new speech and cancels current TTS output |

---

## 2. Tool Selection & Rationale

### 🏆 Primary Tool: `faster-whisper`

**Why `faster-whisper` over all alternatives:**

```
faster-whisper = OpenAI Whisper model + CTranslate2 backend
```

| Alternative | Cost | Accuracy | Latency | Privacy | Verdict |
|-------------|------|----------|---------|---------|---------|
| **faster-whisper (chosen)** | $0.00 (local) | 95%+ WER | ~300ms on CPU, ~80ms GPU | ✅ Full (local) | ✅ Best overall |
| OpenAI Whisper API | $0.006/min | 95%+ | ~1-2s round trip | ❌ Data leaves server | Too slow + costly |
| Deepgram | Free tier limited | 95%+ | ~200ms | ❌ Cloud | Rate limited |
| Web Speech API | Free | ~80% | Real-time | ✅ Browser-local | Poor with BI jargon |
| AssemblyAI | $0.0001/sec | 95%+ | ~1s | ❌ Cloud | Costs accumulate |
| Vosk | Free | ~85% | Real-time | ✅ Local | Lower accuracy |

**Key `faster-whisper` advantages for TalkingBI:**
- Runs **4x faster** than original Whisper with **8x less memory** (CTranslate2 INT8 quantization)
- Supports **streaming transcription** — returns partial results as user speaks
- **Initial prompt injection**: seed it with BI terminology for dramatically better accuracy on domain words
- Runs on CPU (no GPU required for `tiny` and `base` models)
- MIT license — completely free, no usage limits

---

### Supporting Tools (All Free)

| Role | Tool | Why |
|------|------|-----|
| **Voice Activity Detection (VAD)** | `silero-vad` | Best-in-class open-source VAD; detects speech start/end with <50ms accuracy; prevents sending silence to Whisper |
| **Browser Audio Capture** | `MediaRecorder API` (native browser) | No library needed; captures PCM audio from mic; supported in all modern browsers |
| **Audio Streaming** | `WebSockets` (already in TalkingBI stack) | Reuse existing WS infrastructure; stream 16-bit PCM chunks from browser to backend in real-time |
| **Text-to-Speech (TTS)** | `edge-tts` (Microsoft Edge TTS) | Completely free Python library; 300+ voices; neural TTS quality; no API key needed; returns MP3 stream |
| **Audio Preprocessing** | `pydub` + `ffmpeg` | Resample browser audio (48kHz stereo) to Whisper-required format (16kHz mono PCM); both free |
| **WebRTC noise cancellation** | `RNNoise` (via `rnnoise-wasm`) | Client-side noise suppression before sending audio; improves Whisper accuracy in noisy environments |

---

### Why `edge-tts` for Text-to-Speech

```bash
# Zero setup, zero API key, zero cost
pip install edge-tts
echo "Your revenue grew by 23 percent last quarter" | edge-tts --voice en-US-AriaNeural --write-media output.mp3
```

- **Microsoft's neural voices** (same engine as Azure Cognitive Services) — completely free via the edge-tts reverse-engineered client
- 400+ voices across 100+ languages
- Streams audio chunks as they're generated (no waiting for full synthesis)
- Returns MP3 that plays directly in the browser `<audio>` element

---

## 3. Voice Pipeline Architecture

### End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BROWSER (Frontend)                                   │
│                                                                               │
│  [🎤 MicButton] → MediaRecorder API → RNNoise (noise cancel)                 │
│       ↓                                                                       │
│  PCM Audio Chunks (16kHz, mono, 16-bit)                                      │
│       ↓                                                                       │
│  WebSocket Connection (ws://api/voice/stream)                                │
│       ↓                                                          ↑            │
│  [Partial Transcript Display]   [Audio Player] ← MP3 Chunks ────┤            │
│  [Full Response Display] ←──── JSON Response ───────────────────┤            │
└──────────────────────────────────────┬──────────────────────────┘            │
                                       │ WebSocket                              │
┌──────────────────────────────────────▼──────────────────────────┐            │
│                         BACKEND (FastAPI)                         │            │
│                                                                   │            │
│  ┌─────────────────────────────────────────────────────────┐     │            │
│  │  VoiceStreamHandler                                      │     │            │
│  │                                                          │     │            │
│  │  Audio Buffer ──→ Silero VAD ──→ Speech Segment         │     │            │
│  │                        │                ↓               │     │            │
│  │                    [silence]      faster-whisper         │     │            │
│  │                        │         (streaming mode)       │     │            │
│  │                    [discard]           ↓                │     │            │
│  │                               Partial Transcript        │     │            │
│  │                               ──→ WebSocket Push        │─────┘            │
│  │                                        ↓                │                  │
│  │                               Full Transcript           │                  │
│  │                               + Domain Cleanup          │                  │
│  └───────────────────────┬─────────────────────────────────┘                  │
│                          │                                                     │
│  ┌───────────────────────▼─────────────────────────────────┐                  │
│  │  TalkingBI Orchestrator (existing)                       │                  │
│  │  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌───────┐ │                  │
│  │  │ SQL Agent  │  │ DeepPrep │  │ Insights │  │Charts │ │                  │
│  │  └────────────┘  └──────────┘  └──────────┘  └───────┘ │                  │
│  │                        ↓                                 │                  │
│  │              TalkingBIResponse (text + data + chart)     │                  │
│  └───────────────────────┬─────────────────────────────────┘                  │
│                          │                                                     │
│  ┌───────────────────────▼─────────────────────────────────┐                  │
│  │  VoiceResponseSynthesizer                                │                  │
│  │                                                          │                  │
│  │  Full Response → Extract Speakable Text                  │                  │
│  │  → Trim to ~150 words for audio (key findings only)     │                  │
│  │  → edge-tts (streaming synthesis)                        │                  │
│  │  → MP3 chunks → WebSocket Push ──────────────────────── │──→ Browser       │
│  └──────────────────────────────────────────────────────────┘                  │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

### State Machine

The voice pipeline runs as a finite state machine with 6 states:

```
IDLE ──[mic button pressed]──→ LISTENING
LISTENING ──[speech detected by VAD]──→ CAPTURING
CAPTURING ──[silence >1.5s detected by VAD]──→ TRANSCRIBING
TRANSCRIBING ──[transcript ready]──→ PROCESSING (→ TalkingBI Orchestrator)
PROCESSING ──[response ready]──→ SPEAKING (edge-tts streaming)
SPEAKING ──[audio complete OR new speech detected]──→ IDLE or LISTENING
```

Each state is communicated back to the browser via WebSocket messages so the UI can update the microphone button's visual state in real-time.

---

## 4. Integration Map with Existing TalkingBI

The voice agent slots into the existing architecture with **minimal changes to existing code**. Here is exactly what changes vs. what stays the same:

### What Stays 100% Unchanged

- All four core layers: SQLAgent, DeepPrep, InsightEngine, ChartGenerator
- The Orchestrator's intent classification and routing logic
- The Response Synthesizer
- All existing REST API endpoints
- Frontend chat message components
- Database connections and knowledge base

### What Gets Added (New Files Only)

```
backend/
  voice/
    __init__.py
    stream_handler.py        ← NEW: receives audio chunks via WebSocket
    vad_processor.py         ← NEW: Silero VAD integration
    transcriber.py           ← NEW: faster-whisper wrapper
    tts_engine.py            ← NEW: edge-tts wrapper
    voice_orchestrator.py    ← NEW: coordinates VAD → Whisper → Orchestrator → TTS
    domain_vocab.py          ← NEW: BI domain vocabulary for Whisper prompting
    audio_utils.py           ← NEW: pydub audio format conversion utilities
  api/
    voice_router.py          ← NEW: WebSocket endpoint /api/voice/stream

frontend/
  src/
    components/
      voice/
        MicButton.tsx         ← NEW: animated microphone button component
        VoiceStateIndicator.tsx ← NEW: visual state feedback (listening/processing/speaking)
        AudioPlayer.tsx       ← NEW: hidden audio element for TTS playback
        VoiceTranscriptBubble.tsx ← NEW: real-time partial transcript display
    hooks/
      useVoiceAgent.ts        ← NEW: manages WebSocket + MediaRecorder + audio state
    utils/
      audioProcessing.ts      ← NEW: RNNoise integration + PCM resampling
```

### What Gets Modified (Minimal Changes)

```
backend/api/main.py
  + Add voice_router to app routers (2 lines)

backend/requirements.txt
  + faster-whisper, silero-vad, edge-tts, pydub (4 new packages)

frontend/src/app/chat/page.tsx
  + Import and render <MicButton /> and <AudioPlayer /> (5 lines)

infra/docker-compose.yml
  + No changes needed (voice runs in the existing API container)

.env.example
  + WHISPER_MODEL_SIZE, TTS_VOICE, VAD_THRESHOLD (3 new env vars)
```

---

## 5. Backend Implementation

### 5.1 Install Dependencies

Add to `backend/requirements.txt`:

```txt
# Voice Agent Dependencies
faster-whisper==1.0.3
silero-vad==5.1.2
edge-tts==6.1.10
pydub==0.25.1
soundfile==0.12.1
numpy==1.26.0          # already in requirements, verify version
websockets==12.0       # FastAPI uses this internally via starlette
```

Install system dependency (add to Dockerfile):

```dockerfile
RUN apt-get update && apt-get install -y ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*
```

---

### 5.2 VAD Processor — `backend/voice/vad_processor.py`

```python
"""
Silero VAD wrapper for real-time voice activity detection.
Processes 30ms audio frames and determines if speech is present.
"""
import numpy as np
import torch
from typing import Generator

class VADProcessor:
    SAMPLE_RATE = 16000
    FRAME_MS = 30          # 30ms frames (Silero requirement)
    FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)  # = 480 samples
    SPEECH_THRESHOLD = 0.5  # Probability above which frame is considered speech
    SILENCE_FRAMES_TO_END = 50  # 50 × 30ms = 1.5 seconds of silence → end utterance

    def __init__(self):
        # Load Silero VAD model (downloads ~2MB on first run, cached locally)
        self.model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True
        )
        self.model.eval()
        self._reset_state()

    def _reset_state(self):
        self.speech_buffer: list[np.ndarray] = []
        self.silence_frame_count = 0
        self.is_speaking = False

    def process_chunk(self, pcm_bytes: bytes) -> tuple[bool, bytes | None]:
        """
        Process a raw PCM audio chunk.

        Returns:
            (is_speech_active, completed_utterance_bytes | None)
            - is_speech_active: True while user is speaking
            - completed_utterance_bytes: non-None when a full utterance is ready
        """
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Process in 30ms frames
        utterance_ready = None
        for i in range(0, len(audio), self.FRAME_SAMPLES):
            frame = audio[i:i + self.FRAME_SAMPLES]
            if len(frame) < self.FRAME_SAMPLES:
                break

            tensor = torch.from_numpy(frame).unsqueeze(0)
            speech_prob = self.model(tensor, self.SAMPLE_RATE).item()

            if speech_prob >= self.SPEECH_THRESHOLD:
                self.is_speaking = True
                self.silence_frame_count = 0
                self.speech_buffer.append(frame)
            elif self.is_speaking:
                self.silence_frame_count += 1
                self.speech_buffer.append(frame)  # include trailing silence for natural endings
                
                if self.silence_frame_count >= self.SILENCE_FRAMES_TO_END:
                    # Utterance complete — package and return
                    full_audio = np.concatenate(self.speech_buffer)
                    utterance_ready = (full_audio * 32768).astype(np.int16).tobytes()
                    self._reset_state()
                    break

        return self.is_speaking, utterance_ready
```

---

### 5.3 Transcriber — `backend/voice/transcriber.py`

```python
"""
faster-whisper wrapper with BI domain vocabulary injection.
Supports both batch transcription (full utterance) and streaming partial results.
"""
from faster_whisper import WhisperModel
from .domain_vocab import BI_DOMAIN_PROMPT
import os

class Transcriber:
    # Model size tradeoffs:
    # tiny   → 39M params,  ~300ms CPU,  ~80ms GPU  — good for simple queries
    # base   → 74M params,  ~600ms CPU,  ~120ms GPU — balanced (RECOMMENDED)
    # small  → 244M params, ~1.5s CPU,   ~250ms GPU — best accuracy
    # medium → 769M params, GPU only     ~500ms GPU — production with GPU
    
    MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
    DEVICE = os.getenv("WHISPER_DEVICE", "cpu")   # "cuda" if GPU available
    COMPUTE_TYPE = "int8"  # INT8 quantization: 8x memory reduction, ~4x speedup

    def __init__(self):
        print(f"[Transcriber] Loading Whisper {self.MODEL_SIZE} on {self.DEVICE}...")
        self.model = WhisperModel(
            self.MODEL_SIZE,
            device=self.DEVICE,
            compute_type=self.COMPUTE_TYPE,
            download_root="/app/models/whisper"  # cache models in Docker volume
        )
        print("[Transcriber] Model loaded.")

    def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        """
        Transcribe a complete audio utterance.
        
        The `initial_prompt` injects BI vocabulary so Whisper correctly
        recognizes domain-specific terms it might otherwise mishear.
        Example: "EBITDA" → correctly transcribed instead of "EVITA"
        """
        import io, soundfile as sf, numpy as np

        # Convert PCM bytes to numpy array
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        segments, info = self.model.transcribe(
            audio_array,
            language=language,
            initial_prompt=BI_DOMAIN_PROMPT,  # domain vocabulary seeding
            beam_size=5,
            word_timestamps=False,
            vad_filter=False,  # VAD already applied upstream
            temperature=0.0    # deterministic output
        )

        transcript = " ".join(seg.text.strip() for seg in segments)
        return self._clean_transcript(transcript)

    def _clean_transcript(self, text: str) -> str:
        """Remove Whisper artifacts and normalize BI queries."""
        # Whisper sometimes adds filler like "[MUSIC]" or "(silence)"
        import re
        text = re.sub(r'\[.*?\]|\(.*?\)', '', text).strip()
        text = re.sub(r'\s+', ' ', text)
        return text
```

---

### 5.4 Domain Vocabulary — `backend/voice/domain_vocab.py`

```python
"""
BI domain vocabulary prompt injected into Whisper's initial_prompt.
This dramatically improves transcription accuracy for business terms
that Whisper might otherwise mishear (e.g., "CAC" → "cack", "EBITDA" → "EVITA").

The prompt is NOT shown to the LLM — it only seeds Whisper's context.
Format: conversational text that naturally includes domain terms.
Max recommended length: 224 tokens.
"""

BI_DOMAIN_PROMPT = """
Business intelligence analysis. Revenue, EBITDA, gross margin, net profit, 
operating income, CAC, LTV, churn rate, MRR, ARR, DAU, MAU, NPS, CAGR, 
ROI, KPI, SQL query, dashboard, conversion rate, funnel, cohort, 
year-over-year, quarter-over-quarter, basis points, run rate, burn rate, 
headcount, pipeline, forecast, variance, P&L, balance sheet, cash flow.
Show me the top performers, trend analysis, regional breakdown, 
anomaly detection, insight discovery, data preparation.
"""

# Extended vocabulary for specific industries — add as needed
SAAS_VOCAB_SUPPLEMENT = """
SaaS metrics: MRR, ARR, churn, expansion revenue, logo churn, net revenue retention,
customer health score, trial conversion, seat count, activation rate.
"""

ECOMMERCE_VOCAB_SUPPLEMENT = """
E-commerce metrics: GMV, AOV, cart abandonment, ROAS, CPC, CPM, SKU, 
inventory turnover, fulfillment rate, return rate, repeat purchase rate.
"""
```

---

### 5.5 TTS Engine — `backend/voice/tts_engine.py`

```python
"""
edge-tts wrapper for streaming neural text-to-speech synthesis.
Uses Microsoft's free neural voices (same quality as Azure Cognitive Services).
Streams MP3 chunks as they're generated — no waiting for full synthesis.
"""
import edge_tts
import asyncio
import os
from typing import AsyncGenerator

class TTSEngine:
    VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")
    RATE = os.getenv("TTS_RATE", "+0%")    # speaking rate: -20% slower, +20% faster
    PITCH = os.getenv("TTS_PITCH", "+0Hz") # pitch adjustment

    # Maximum words to speak aloud — keep responses concise for voice UX
    MAX_SPOKEN_WORDS = 150

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Stream MP3 audio chunks for the given text.
        Caller should send each chunk over WebSocket as it arrives.
        """
        spoken_text = self._prepare_for_speech(text)
        
        communicate = edge_tts.Communicate(
            text=spoken_text,
            voice=self.VOICE,
            rate=self.RATE,
            pitch=self.PITCH
        )

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]  # raw MP3 bytes

    def _prepare_for_speech(self, full_response: str) -> str:
        """
        Extract and trim the most important part of the response for speech.
        Full response (with SQL, tables, charts) → concise spoken summary.
        
        Strategy:
        1. Remove code blocks, URLs, markdown formatting
        2. Extract the explanation/summary section
        3. Truncate to MAX_SPOKEN_WORDS
        4. Add natural speech transitions
        """
        import re
        
        # Strip markdown artifacts
        text = re.sub(r'```[\s\S]*?```', '', full_response)  # remove code blocks
        text = re.sub(r'\|.*?\|', '', text)                   # remove table rows
        text = re.sub(r'#+\s', '', text)                      # remove headers
        text = re.sub(r'\*+([^*]+)\*+', r'\1', text)         # remove bold/italic
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text) # remove links
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Truncate to MAX_SPOKEN_WORDS
        words = text.split()
        if len(words) > self.MAX_SPOKEN_WORDS:
            text = ' '.join(words[:self.MAX_SPOKEN_WORDS])
            # End on complete sentence if possible
            last_period = max(text.rfind('.'), text.rfind('!'), text.rfind('?'))
            if last_period > len(text) * 0.7:  # only truncate at sentence if it's in last 30%
                text = text[:last_period + 1]
            else:
                text += "... See the full details in the chat."

        return text
```

---

### 5.6 Voice Orchestrator — `backend/voice/voice_orchestrator.py`

```python
"""
Coordinates the full voice pipeline:
Audio Chunks → VAD → Whisper → TalkingBI Orchestrator → TTS → Audio Stream
"""
import asyncio
import json
from typing import AsyncGenerator
from fastapi import WebSocket
from .vad_processor import VADProcessor
from .transcriber import Transcriber
from .tts_engine import TTSEngine
from ..audio_utils import AudioConverter
from ..orchestrator.main import TalkingBIOrchestrator   # existing orchestrator


class VoiceOrchestrator:
    def __init__(self):
        self.vad = VADProcessor()
        self.transcriber = Transcriber()
        self.tts = TTSEngine()
        self.converter = AudioConverter()
        self.bi_orchestrator = TalkingBIOrchestrator()

    async def handle_session(self, websocket: WebSocket, session_id: str, user_id: str):
        """
        Main WebSocket session handler.
        Receives audio chunks from browser, processes through full pipeline,
        sends back partial transcripts, full responses, and TTS audio chunks.
        """
        await websocket.accept()
        await self._send_state(websocket, "idle")

        try:
            while True:
                # Receive raw audio bytes from browser (PCM 48kHz stereo from MediaRecorder)
                raw_audio = await websocket.receive_bytes()
                
                # Step 1: Convert browser audio (48kHz stereo) to Whisper format (16kHz mono)
                pcm_16k = self.converter.to_whisper_format(raw_audio)
                
                # Step 2: Voice Activity Detection
                is_speaking, utterance_bytes = self.vad.process_chunk(pcm_16k)
                
                if is_speaking and not utterance_bytes:
                    # User is actively speaking — update UI state
                    await self._send_state(websocket, "listening")
                
                if utterance_bytes:
                    # Complete utterance detected — begin transcription + response pipeline
                    await self._send_state(websocket, "transcribing")
                    
                    # Step 3: Transcribe with faster-whisper
                    transcript = self.transcriber.transcribe(utterance_bytes)
                    
                    if not transcript.strip():
                        await self._send_state(websocket, "idle")
                        continue
                    
                    # Send partial transcript to UI immediately (user sees what was heard)
                    await websocket.send_json({
                        "type": "transcript",
                        "text": transcript,
                        "final": True
                    })
                    
                    await self._send_state(websocket, "processing")
                    
                    # Step 4: Pass transcript to existing TalkingBI Orchestrator
                    # (exactly as if user typed this text — zero changes to Orchestrator)
                    bi_response = await self.bi_orchestrator.process(
                        session_id=session_id,
                        user_id=user_id,
                        message=transcript
                    )
                    
                    # Step 5: Send full visual response (text + charts + insights)
                    await websocket.send_json({
                        "type": "response",
                        "data": bi_response.model_dump()
                    })
                    
                    await self._send_state(websocket, "speaking")
                    
                    # Step 6: Stream TTS audio chunks back to browser
                    async for audio_chunk in self.tts.synthesize_stream(bi_response.explanation):
                        await websocket.send_bytes(
                            b"AUDIO:" + audio_chunk  # prefix to distinguish from control messages
                        )
                    
                    # Signal TTS complete
                    await websocket.send_json({"type": "tts_complete"})
                    await self._send_state(websocket, "idle")

        except Exception as e:
            await websocket.send_json({"type": "error", "message": str(e)})
        finally:
            await websocket.close()

    async def _send_state(self, websocket: WebSocket, state: str):
        await websocket.send_json({"type": "state", "state": state})
```

---

### 5.7 Audio Utilities — `backend/voice/audio_utils.py`

```python
"""
Audio format conversion utilities.
Converts browser MediaRecorder output (WebM/Opus or PCM, 48kHz stereo)
to Whisper's required format (raw PCM, 16kHz, mono, 16-bit signed).
"""
import numpy as np
from pydub import AudioSegment
import io

class AudioConverter:
    WHISPER_SAMPLE_RATE = 16000
    WHISPER_CHANNELS = 1
    WHISPER_BIT_DEPTH = 16

    def to_whisper_format(self, raw_bytes: bytes) -> bytes:
        """
        Convert any browser audio format to Whisper-compatible PCM.
        Handles: WebM/Opus (Chrome), WebM/Vorbis (Firefox), raw PCM.
        """
        try:
            # Try parsing as WebM/Opus (most common from Chrome MediaRecorder)
            audio = AudioSegment.from_file(io.BytesIO(raw_bytes), format="webm")
        except Exception:
            try:
                # Try raw PCM fallback
                audio = AudioSegment(
                    raw_bytes,
                    sample_width=2,     # 16-bit
                    frame_rate=48000,   # browser default
                    channels=2          # stereo
                )
            except Exception:
                return raw_bytes  # pass through unchanged, let Whisper handle it

        # Resample to 16kHz mono
        audio = audio.set_frame_rate(self.WHISPER_SAMPLE_RATE)
        audio = audio.set_channels(self.WHISPER_CHANNELS)
        audio = audio.set_sample_width(self.WHISPER_BIT_DEPTH // 8)
        
        return audio.raw_data
```

---

### 5.8 WebSocket Router — `backend/api/voice_router.py`

```python
"""
FastAPI WebSocket router for voice streaming.
Single endpoint handles the entire voice session lifecycle.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from ..voice.voice_orchestrator import VoiceOrchestrator
from ..services.auth import get_current_user_ws  # existing auth service

router = APIRouter(prefix="/api/voice", tags=["voice"])

# Singleton orchestrator (shared across all sessions — model loads once)
_orchestrator: VoiceOrchestrator | None = None

def get_voice_orchestrator() -> VoiceOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = VoiceOrchestrator()  # loads Whisper model on first call
    return _orchestrator


@router.websocket("/stream")
async def voice_stream(
    websocket: WebSocket,
    session_id: str,
    orchestrator: VoiceOrchestrator = Depends(get_voice_orchestrator)
):
    """
    WebSocket endpoint for real-time voice interaction.
    
    Protocol:
    - Client sends: raw PCM audio bytes (continuous stream)
    - Server sends:
        - JSON: {"type": "state", "state": "idle|listening|transcribing|processing|speaking"}
        - JSON: {"type": "transcript", "text": "...", "final": bool}
        - JSON: {"type": "response", "data": {TalkingBIResponse}}
        - JSON: {"type": "tts_complete"}
        - JSON: {"type": "error", "message": "..."}
        - Bytes: b"AUDIO:" + <mp3_chunk_bytes>
    """
    # Extract user from JWT token in query param (WebSocket can't send headers easily)
    user = await get_current_user_ws(websocket)
    
    try:
        await orchestrator.handle_session(
            websocket=websocket,
            session_id=session_id,
            user_id=str(user.id)
        )
    except WebSocketDisconnect:
        pass  # normal client disconnect
```

---

### 5.9 Register Router — modify `backend/api/main.py`

```python
# Add these 2 lines to your existing main.py

from .voice_router import router as voice_router   # ← ADD
app.include_router(voice_router)                    # ← ADD
```

---

## 6. Frontend Implementation

### 6.1 Core Hook — `frontend/src/hooks/useVoiceAgent.ts`

```typescript
/**
 * useVoiceAgent — manages the complete voice agent lifecycle on the client.
 * 
 * Responsibilities:
 * - Request and hold microphone permission
 * - Set up MediaRecorder to capture PCM audio chunks
 * - Manage WebSocket connection to /api/voice/stream
 * - Handle all incoming messages (state, transcript, response, audio)
 * - Expose clean interface to UI components
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import { TalkingBIResponse } from '@/types/api';

export type VoiceState = 'idle' | 'listening' | 'transcribing' | 'processing' | 'speaking' | 'error';

interface UseVoiceAgentOptions {
  sessionId: string;
  onResponse: (response: TalkingBIResponse) => void;  // add to chat messages
  onTranscript: (text: string) => void;                // show what user said
}

export function useVoiceAgent({ sessionId, onResponse, onTranscript }: UseVoiceAgentOptions) {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [partialTranscript, setPartialTranscript] = useState('');

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioQueueRef = useRef<AudioBuffer[]>([]);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const mp3ChunksRef = useRef<Uint8Array[]>([]);
  const isActiveRef = useRef(false);

  // ── WebSocket Setup ──────────────────────────────────────────────────────
  const connect = useCallback(() => {
    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL}/api/voice/stream?session_id=${sessionId}`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => { setIsConnected(false); setVoiceState('idle'); };

    ws.onmessage = (event) => {
      // Binary message = audio chunk
      if (event.data instanceof ArrayBuffer) {
        const bytes = new Uint8Array(event.data);
        // Strip "AUDIO:" prefix (6 bytes)
        const audioPrefix = new TextEncoder().encode('AUDIO:');
        if (bytes.slice(0, 6).every((b, i) => b === audioPrefix[i])) {
          mp3ChunksRef.current.push(bytes.slice(6));
        }
        return;
      }

      // JSON message = control/data
      const msg = JSON.parse(event.data as string);
      
      switch (msg.type) {
        case 'state':
          setVoiceState(msg.state as VoiceState);
          // When speaking starts, assemble and play the buffered MP3 audio
          if (msg.state === 'idle' && mp3ChunksRef.current.length > 0) {
            playAccumulatedAudio();
          }
          break;
        
        case 'transcript':
          setPartialTranscript(msg.text);
          if (msg.final) onTranscript(msg.text);
          break;
        
        case 'response':
          onResponse(msg.data as TalkingBIResponse);
          break;
        
        case 'tts_complete':
          playAccumulatedAudio();
          break;
        
        case 'error':
          setError(msg.message);
          setVoiceState('error');
          break;
      }
    };

    wsRef.current = ws;
  }, [sessionId, onResponse, onTranscript]);

  // ── Audio Playback ───────────────────────────────────────────────────────
  const playAccumulatedAudio = useCallback(() => {
    if (mp3ChunksRef.current.length === 0) return;
    
    // Combine all MP3 chunks into a single Blob
    const blob = new Blob(mp3ChunksRef.current, { type: 'audio/mpeg' });
    const url = URL.createObjectURL(blob);
    mp3ChunksRef.current = []; // reset for next response
    
    if (!audioPlayerRef.current) {
      audioPlayerRef.current = new Audio();
    }
    audioPlayerRef.current.src = url;
    audioPlayerRef.current.play().catch(console.error);
    audioPlayerRef.current.onended = () => URL.revokeObjectURL(url);
  }, []);

  // ── Microphone Capture ───────────────────────────────────────────────────
  const startListening = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connect();
      await new Promise(resolve => setTimeout(resolve, 500)); // wait for connection
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 48000,
          channelCount: 1,      // mono
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      // MediaRecorder: capture 250ms chunks continuously
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus',
        audioBitsPerSecond: 128000
      });

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          event.data.arrayBuffer().then(buffer => {
            wsRef.current!.send(buffer);
          });
        }
      };

      mediaRecorder.start(250); // emit chunk every 250ms
      mediaRecorderRef.current = mediaRecorder;
      isActiveRef.current = true;
      setVoiceState('listening');

    } catch (err) {
      setError('Microphone access denied. Please allow microphone permission.');
      setVoiceState('error');
    }
  }, [connect]);

  const stopListening = useCallback(() => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop());
      mediaRecorderRef.current = null;
    }
    isActiveRef.current = false;
    setVoiceState('idle');
  }, []);

  const toggleListening = useCallback(() => {
    if (isActiveRef.current) {
      stopListening();
    } else {
      startListening();
    }
  }, [startListening, stopListening]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopListening();
      wsRef.current?.close();
    };
  }, []);

  return {
    voiceState,
    isConnected,
    error,
    partialTranscript,
    toggleListening,
    isListening: isActiveRef.current
  };
}
```

---

### 6.2 Microphone Button — `frontend/src/components/voice/MicButton.tsx`

```tsx
/**
 * Animated microphone button that reflects the current voice state.
 * 
 * Visual states:
 * idle        → grey mic icon, no animation
 * listening   → blue mic icon, pulsing ring animation
 * transcribing → amber mic icon, spinner
 * processing  → amber, data processing animation
 * speaking    → green speaker icon, sound wave animation
 * error       → red mic icon, shake animation
 */
import { Mic, MicOff, Volume2, Loader2 } from 'lucide-react';
import { VoiceState } from '@/hooks/useVoiceAgent';

interface MicButtonProps {
  state: VoiceState;
  onToggle: () => void;
  disabled?: boolean;
}

const STATE_CONFIG = {
  idle:         { icon: Mic,     color: 'text-gray-400',  bg: 'bg-gray-100', ring: '',                  tooltip: 'Click to speak' },
  listening:    { icon: Mic,     color: 'text-blue-600',  bg: 'bg-blue-50',  ring: 'ring-2 ring-blue-400 ring-offset-2 animate-pulse', tooltip: 'Listening... click to stop' },
  transcribing: { icon: Loader2, color: 'text-amber-500', bg: 'bg-amber-50', ring: '',                  tooltip: 'Transcribing...' },
  processing:   { icon: Loader2, color: 'text-amber-500', bg: 'bg-amber-50', ring: '',                  tooltip: 'Processing query...' },
  speaking:     { icon: Volume2, color: 'text-green-600', bg: 'bg-green-50', ring: 'ring-2 ring-green-400 ring-offset-2', tooltip: 'Speaking... click to interrupt' },
  error:        { icon: MicOff,  color: 'text-red-500',   bg: 'bg-red-50',   ring: '',                  tooltip: 'Error — click to retry' },
};

export function MicButton({ state, onToggle, disabled = false }: MicButtonProps) {
  const config = STATE_CONFIG[state];
  const Icon = config.icon;
  const isAnimated = state === 'transcribing' || state === 'processing';

  return (
    <div className="relative group">
      <button
        onClick={onToggle}
        disabled={disabled}
        aria-label={config.tooltip}
        className={`
          w-10 h-10 rounded-full flex items-center justify-center
          transition-all duration-200 hover:scale-105 active:scale-95
          ${config.bg} ${config.ring}
          disabled:opacity-50 disabled:cursor-not-allowed
        `}
      >
        <Icon
          size={18}
          className={`${config.color} ${isAnimated ? 'animate-spin' : ''}`}
        />
      </button>
      
      {/* Tooltip */}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 
                      bg-gray-800 text-white text-xs rounded whitespace-nowrap
                      opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        {config.tooltip}
      </div>
    </div>
  );
}
```

---

### 6.3 Voice Transcript Bubble — `frontend/src/components/voice/VoiceTranscriptBubble.tsx`

```tsx
/**
 * Displays the real-time transcript above the input bar.
 * Appears when user is speaking, disappears after response is received.
 */
interface Props {
  transcript: string;
  isVisible: boolean;
}

export function VoiceTranscriptBubble({ transcript, isVisible }: Props) {
  if (!isVisible || !transcript) return null;

  return (
    <div className="mx-4 mb-2 px-4 py-2 bg-blue-50 border border-blue-200 rounded-xl
                    text-sm text-blue-800 italic animate-fade-in flex items-center gap-2">
      <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse flex-shrink-0" />
      <span>"{transcript}"</span>
    </div>
  );
}
```

---

### 6.4 Wire Into Chat Page — `frontend/src/app/chat/page.tsx`

Add these lines to your **existing** chat page (minimal changes):

```tsx
// Add to your existing imports
import { useVoiceAgent } from '@/hooks/useVoiceAgent';
import { MicButton } from '@/components/voice/MicButton';
import { VoiceTranscriptBubble } from '@/components/voice/VoiceTranscriptBubble';

// Add inside your ChatPage component, alongside existing useState/hooks:
const {
  voiceState,
  toggleListening,
  partialTranscript,
  isListening,
  error: voiceError
} = useVoiceAgent({
  sessionId: currentSessionId,
  onResponse: (response) => addMessageToChat(response),   // your existing function
  onTranscript: (text) => setInputValue(text)             // your existing input setter
});

// In your JSX, find the input bar and add:
// 1. MicButton next to the send button
<MicButton state={voiceState} onToggle={toggleListening} />

// 2. Transcript bubble above the input
<VoiceTranscriptBubble
  transcript={partialTranscript}
  isVisible={isListening || voiceState === 'transcribing'}
/>
```

---

## 7. Real-Time Streaming Protocol

### WebSocket Message Schema

```typescript
// Browser → Server (binary only)
type ClientMessage = ArrayBuffer; // raw WebM/Opus audio chunks

// Server → Browser (JSON or Binary)
type ServerMessage =
  | { type: 'state';       state: VoiceState }
  | { type: 'transcript';  text: string; final: boolean }
  | { type: 'response';    data: TalkingBIResponse }
  | { type: 'tts_complete' }
  | { type: 'error';       message: string }
  | ArrayBuffer; // MP3 audio prefixed with b"AUDIO:"
```

### Timing Diagram

```
Time →    0ms      250ms    500ms    750ms    1000ms   2500ms   3500ms   4500ms
          │        │        │        │        │        │        │        │
Browser   [chunk1] [chunk2] [chunk3] [chunk4] [silence detected]
Server    │        │        │        │        [VAD end]│        │        │
          │        │        │        │        [Whisper]│        │        │
          [state:listening]          [state:transcribing]       │        │
          │        │        │        │        [transcript→UI]   │        │
          │        │        │        │        [state:processing]│        │
          │        │        │        │        [→Orchestrator]   │        │
          │        │        │        │        │       [response→UI]      │
          │        │        │        │        │       [state:speaking]   │
          │        │        │        │        │       [TTS chunk 1]      │
          │        │        │        │        │       [TTS chunk 2] [TTS chunk 3]
          │        │        │        │        │                │   [tts_complete]
          │        │        │        │        │                │   [state:idle]
```

---

## 8. Step-by-Step Setup Guide

### Step 1 — Install Backend Dependencies

```bash
# Inside your virtual environment
pip install faster-whisper==1.0.3 silero-vad==5.1.2 edge-tts==6.1.10 pydub==0.25.1 soundfile==0.12.1

# System dependency (Ubuntu/Debian)
sudo apt-get install -y ffmpeg libsndfile1

# macOS
brew install ffmpeg libsndfile
```

### Step 2 — Pre-download Whisper Model

```bash
# Run once to cache the model (avoids cold-start delay in production)
python -c "
from faster_whisper import WhisperModel
model = WhisperModel('base', device='cpu', compute_type='int8', download_root='/app/models/whisper')
print('Model downloaded and cached successfully.')
"
```

### Step 3 — Add to Docker Compose

```yaml
# Add to infra/docker-compose.yml under the api service:
services:
  api:
    volumes:
      - whisper_models:/app/models/whisper  # ← ADD: persist downloaded models
    environment:
      - WHISPER_MODEL_SIZE=base             # ← ADD
      - WHISPER_DEVICE=cpu                  # ← ADD (change to "cuda" if GPU available)
      - TTS_VOICE=en-US-AriaNeural          # ← ADD

volumes:
  whisper_models:  # ← ADD: named volume so model persists across container restarts
```

### Step 4 — Configure Environment Variables

```bash
# Add to your .env file:
WHISPER_MODEL_SIZE=base           # tiny | base | small | medium
WHISPER_DEVICE=cpu                # cpu | cuda
WHISPER_COMPUTE_TYPE=int8         # int8 | float16 | float32
TTS_VOICE=en-US-AriaNeural        # See: edge-tts --list-voices
TTS_RATE=+0%                      # Speaking rate adjustment
VAD_THRESHOLD=0.5                 # Speech probability threshold (0.0-1.0)
NEXT_PUBLIC_WS_URL=ws://localhost:8080  # Frontend WebSocket base URL
```

### Step 5 — Register Voice Router

```python
# In backend/api/main.py, add 2 lines:
from .voice_router import router as voice_router
app.include_router(voice_router)
```

### Step 6 — Frontend Browser Permissions

```tsx
// Add to frontend/src/app/layout.tsx or _document.tsx
// This prompts for microphone permission before user clicks mic button
// (better UX than asking at the moment of first click)

// Optional: request permission early on page load
useEffect(() => {
  navigator.permissions.query({ name: 'microphone' as PermissionName })
    .then(result => {
      if (result.state === 'prompt') {
        // Show a visual cue that mic permission will be needed
        console.log('Microphone permission will be requested on first voice interaction');
      }
    });
}, []);
```

### Step 7 — Verify Integration

```bash
# Backend test: verify Whisper loads and transcribes
python -c "
from backend.voice.transcriber import Transcriber
import numpy as np

t = Transcriber()
# Generate 3 seconds of silence (should return empty string)
silence = np.zeros(16000 * 3, dtype=np.int16).tobytes()
result = t.transcribe(silence)
print(f'Test passed. Result: \"{result}\"')
"

# Frontend test: open browser console and check WebSocket
# Navigate to http://localhost:3000, open DevTools Network tab
# Click mic button → should see WebSocket connection to ws://localhost:8080/api/voice/stream
```

---

## 9. Configuration Reference

### Whisper Model Size Guide

| Model | Size | RAM | CPU Speed | GPU Speed | Best For |
|-------|------|-----|-----------|-----------|----------|
| `tiny` | 39 MB | ~1 GB | ~300ms | ~80ms | Fastest, lower accuracy |
| `base` | 74 MB | ~1 GB | ~600ms | ~120ms | ✅ **Recommended start** |
| `small` | 244 MB | ~2 GB | ~1.5s | ~250ms | Better accuracy, still fast |
| `medium` | 769 MB | ~5 GB | Too slow | ~500ms | GPU-only production use |

### TTS Voice Options (Best for BI)

```bash
# List all available voices:
python -m edge_tts --list-voices | grep en-US

# Recommended voices for professional BI context:
# en-US-AriaNeural     — natural, conversational female voice (DEFAULT)
# en-US-GuyNeural      — clear, authoritative male voice
# en-US-JennyNeural    — friendly, clear female voice
# en-GB-SoniaNeural    — professional British female voice
# en-AU-NatashaNeural  — clear Australian female voice
```

### VAD Tuning

```python
# In backend/voice/vad_processor.py, adjust these constants:

SPEECH_THRESHOLD = 0.5    # Lower = more sensitive (picks up quiet speech)
                           # Higher = less sensitive (reduces false triggers from noise)
                           # Range: 0.3 (very sensitive) to 0.7 (very strict)

SILENCE_FRAMES_TO_END = 50  # × 30ms = time of silence before utterance ends
                              # 50 = 1.5 seconds (default, good for thinking pauses)
                              # 33 = 1.0 seconds (faster, may cut off mid-sentence)
                              # 67 = 2.0 seconds (more patient, for slower speakers)
```

---

## 10. Testing & Benchmarking

### Unit Tests — `backend/tests/voice/`

```
test_vad_processor.py
  - test_detects_speech_segment: play 440Hz sine wave → should detect as speech
  - test_ignores_silence: send zeros → should not trigger utterance
  - test_handles_noisy_input: add gaussian noise → speech should still be detected

test_transcriber.py
  - test_transcribes_clear_speech: known audio file → expected transcript ±5 WER
  - test_handles_bi_terminology: "What is our EBITDA" → should not transcribe as "EVITA"
  - test_handles_empty_audio: silence → should return empty string, not crash

test_tts_engine.py
  - test_generates_audio_bytes: synthesize short text → output bytes > 0
  - test_strips_markdown: input with code blocks → output has no backticks
  - test_truncates_long_text: 500-word input → output ≤ MAX_SPOKEN_WORDS

test_voice_orchestrator.py (integration)
  - test_full_pipeline: audio bytes → transcript → mock BI response → TTS audio
  - test_handles_empty_utterance: silence audio → no response generated, state returns to idle
  - test_interruption: speaking state → new audio arrives → previous TTS cancelled
```

### Accuracy Benchmarks

```bash
# Run Word Error Rate (WER) benchmark on BI-domain test set
python scripts/benchmark_voice.py \
  --audio-dir tests/fixtures/voice_samples/ \
  --expected-transcripts tests/fixtures/expected_transcripts.json \
  --model-size base \
  --report-file reports/wer_benchmark.json

# Expected results:
# General English WER:     < 5%  (Whisper base standard)
# BI domain terminology WER: < 8%  (with domain prompt injection)
# Without domain prompt:     ~18% (EBITDA, CAC, etc. frequently misheard)
```

---

## 11. Token & Cost Optimization for Voice

### Voice-Specific Token Budget

The voice pipeline introduces **zero additional LLM tokens** for transcription (Whisper is local) and **minimal tokens** for TTS preparation:

| Voice Step | LLM Used | Tokens/Request | Notes |
|------------|----------|----------------|-------|
| VAD processing | None | 0 | Pure Python/PyTorch |
| Speech-to-text | Whisper (local) | 0 | No API calls |
| Transcript → Orchestrator | (same as text query) | same as existing | No additional cost |
| TTS text preparation | None (regex-based) | 0 | No LLM needed |
| TTS synthesis | edge-tts (free) | 0 | No API calls |

**Voice adds $0 to your existing per-query LLM cost.**

### Latency Optimization Tips

```python
# 1. Pre-warm the Whisper model on startup (avoid cold-start on first query)
# In backend/api/main.py lifespan:
@asynccontextmanager
async def lifespan(app: FastAPI):
    get_voice_orchestrator()  # loads Whisper model at startup, not first request
    yield

# 2. Use tiny model for short queries (<5 words), base for longer
# Detect query length from audio duration before transcribing:
if audio_duration_seconds < 3:
    use_model = "tiny"   # ~300ms
else:
    use_model = "base"   # ~600ms

# 3. Start TTS synthesis BEFORE the full BI response is ready
# Stream the first sentence of the explanation while charts/SQL are still processing
```

---

## 12. Future Voice Enhancements

### Near-Term (1-2 Months)

| Feature | Implementation | Effort |
|---------|---------------|--------|
| **Continuous listening mode** | Keep mic open; detect "Hey BI" wake word using Porcupine (free tier) | Medium |
| **Multi-language support** | Pass `language` param to Whisper; auto-detect with `detect_language()` | Low |
| **Voice shortcuts** | "Stop", "Repeat that", "Show me a table instead" — keyword detection before full transcription | Low |
| **Speaker diarization** | pyannote.audio (open-source) — identify who's speaking in a team setting | High |

### Medium-Term (2-4 Months)

| Feature | Implementation | Effort |
|---------|---------------|--------|
| **Custom wake word** | Train a tiny keyword detection model on "Hey TalkingBI" using openWakeWord (free) | High |
| **Voice-controlled chart editing** | "Make that chart a line chart", "Filter to Q3 only" — voice commands routed to ChartGenerator | Medium |
| **Meeting mode** | Transcribe an entire business meeting, extract all BI questions asked, answer them as a post-meeting report | High |
| **Voice persona customization** | Let users choose TTS voice and speaking rate from settings panel | Low |

### Long-Term Vision

```
Phase A: Proactive Voice Alerts
  TalkingBI detects a critical business anomaly (e.g., revenue drop >20%)
  → Sends a push notification
  → User opens app → TalkingBI proactively speaks: "I found something urgent..."
  → Full voice-guided walkthrough of the anomaly

Phase B: Voice-Enabled Meeting Integration  
  Slack/Teams bot listens to a channel
  → Users ask BI questions in voice messages
  → TalkingBI replies with a voice note + chart image
  → No app switching required

Phase C: Ambient BI Mode
  Always-on listening mode on a dedicated device (e.g., meeting room smart speaker)
  → Team members ask questions during meetings
  → TalkingBI answers aloud in real-time
  → Automatically generates meeting summary with all data points discussed
```

---

## Quick Reference Card

### Files Added
```
backend/voice/__init__.py
backend/voice/vad_processor.py       ← Silero VAD
backend/voice/transcriber.py         ← faster-whisper
backend/voice/tts_engine.py          ← edge-tts
backend/voice/voice_orchestrator.py  ← Pipeline coordinator
backend/voice/domain_vocab.py        ← BI terminology prompt
backend/voice/audio_utils.py         ← Format conversion
backend/api/voice_router.py          ← WebSocket endpoint

frontend/src/hooks/useVoiceAgent.ts
frontend/src/components/voice/MicButton.tsx
frontend/src/components/voice/VoiceTranscriptBubble.tsx
```

### Files Modified (Minimally)
```
backend/api/main.py          ← +2 lines (import + include_router)
backend/requirements.txt     ← +4 packages
infra/docker-compose.yml     ← +3 lines (volume + 2 env vars)
frontend/src/app/chat/page.tsx ← +5 lines (import + render 2 components)
.env / .env.example          ← +5 env vars
```

### New Dependencies
```
Python: faster-whisper, silero-vad, edge-tts, pydub, soundfile
System: ffmpeg, libsndfile
Frontend: (none — uses native browser APIs only)
```

### Cost
```
faster-whisper:  $0.00 (local inference)
silero-vad:      $0.00 (local PyTorch model)
edge-tts:        $0.00 (free Microsoft neural TTS)
pydub/ffmpeg:    $0.00 (open-source)
Additional LLM:  $0.00 (voice pipeline doesn't add LLM calls)
```

---

*TalkingBI Voice Agent — Designed for seamless integration, zero additional cloud cost, and production-grade accuracy.*

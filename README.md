# TalkingBI

TalkingBI is a conversational business intelligence app with a FastAPI backend and a Vite + React frontend.

## Run locally

Backend:

```bash
python -m uvicorn api.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Voice features

The app includes a websocket voice flow at `/voice/stream` plus existing upload-based transcription endpoints.

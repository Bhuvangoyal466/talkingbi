from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LLM_PROVIDER: str = "openrouter"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    GROQ_API_KEY: str = ""
    ASSEMBLYAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    PRIMARY_MODEL: str = "meta-llama/llama-3.1-8b-instruct:free"
    CODE_MODEL: str = "qwen/qwen-2.5-coder-7b-instruct:free"
    EMBED_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    KNOWLEDGE_BASE_DIR: str = "./data/knowledge_base"
    UPLOAD_DIR: str = "./data/uploads"
    CACHE_DIR: str = "./data/cache"
    LOG_LEVEL: str = "INFO"
    MAX_ITER: int = 5
    TOP_K: int = 3

    # Voice settings
    VOICE_USE_LOCAL_TRANSCRIPTION: bool = False
    WHISPER_MODEL_SIZE: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_INITIAL_PROMPT: str = (
        "Business intelligence analysis. Revenue, EBITDA, gross margin, net profit, "
        "operating income, CAC, LTV, churn rate, MRR, ARR, DAU, MAU, NPS, ROI, KPI, "
        "SQL query, dashboard, conversion rate, funnel, cohort, year over year, "
        "quarter over quarter, basis points, run rate, burn rate, forecast, variance."
    )
    TTS_VOICE: str = "en-US-AriaNeural"
    TTS_RATE: str = "+0%"
    TTS_PITCH: str = "+0Hz"
    VOICE_MAX_SPOKEN_WORDS: int = 150

    # Fix 6 — reduced defaults; override in .env if your dataset needs more
    # MAX_EXPLORATION_STEPS: was 20, now 10 (~50% fewer MCTS LLM calls)
    # N_INSIGHT_QUESTIONS:   was 6,  now 4  (~33% fewer insight LLM calls)
    MAX_EXPLORATION_STEPS: int = 10
    N_INSIGHT_QUESTIONS: int = 4


settings = Settings()

# Create required directories (including the new LLM cache dir)
for d in [
    settings.CHROMA_PERSIST_DIR,
    settings.KNOWLEDGE_BASE_DIR,
    settings.UPLOAD_DIR,
    settings.CACHE_DIR,
    "./data/cache/llm",   # Fix 7 — LLM response cache
    "./data/cache/voice",
    "./data/cache/whisper",
]:
    Path(d).mkdir(parents=True, exist_ok=True)
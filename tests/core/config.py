from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LLM_PROVIDER: str = "openrouter"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    GROQ_API_KEY: str = ""
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


settings = Settings()

# Create required directories
for d in [
    settings.CHROMA_PERSIST_DIR,
    settings.KNOWLEDGE_BASE_DIR,
    settings.UPLOAD_DIR,
    settings.CACHE_DIR,
]:
    Path(d).mkdir(parents=True, exist_ok=True)

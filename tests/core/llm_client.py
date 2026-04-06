import json
import requests
from typing import Optional
from core.config import settings
from core.logger import logger
from core.exceptions import LLMError


class LLMClient:
    """
    Unified LLM client supporting Ollama, Groq, and OpenRouter.
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.primary = settings.PRIMARY_MODEL
        self.code_model = settings.CODE_MODEL
        self.base_url = settings.OLLAMA_BASE_URL

    def chat(
        self,
        prompt: str,
        system: str = "",
        model: Optional[str] = None,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> str:
        model = model or self.primary
        try:
            if self.provider == "ollama":
                return self._ollama_chat(prompt, system, model, temperature, json_mode)
            elif self.provider == "groq":
                return self._groq_chat(prompt, system, model, temperature)
            elif self.provider == "openrouter":
                return self._openrouter_chat(prompt, system, model, temperature, json_mode)
            else:
                raise LLMError(f"Unknown provider: {self.provider}")
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise LLMError(str(e)) from e

    def _ollama_chat(
        self,
        prompt: str,
        system: str,
        model: str,
        temperature: float,
        json_mode: bool,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=600,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _groq_chat(
        self, prompt: str, system: str, model: str, temperature: float
    ) -> str:
        from groq import Groq

        client = Groq(api_key=settings.GROQ_API_KEY)
        # Map OpenRouter model IDs to Groq equivalents when switching providers
        groq_model_map = {
            # Current .env models
            "nvidia/nemotron-3-super-120b-a12b:free": "llama-3.3-70b-versatile",
            "minimax/minimax-m2.5:free": "llama-3.3-70b-versatile",
            # Common OpenRouter free models
            "meta-llama/llama-3.1-8b-instruct:free": "llama-3.1-8b-instant",
            "meta-llama/llama-3.1-70b-instruct:free": "llama-3.1-70b-versatile",
            "meta-llama/llama-4-maverick:free": "llama-3.3-70b-versatile",
            "meta-llama/llama-4-scout:free": "llama-3.1-8b-instant",
            "qwen/qwen-2.5-coder-7b-instruct:free": "llama-3.1-8b-instant",
            "mistralai/mistral-7b-instruct:free": "mixtral-8x7b-32768",
            "google/gemma-3-27b-it:free": "llama-3.3-70b-versatile",
            # Legacy Ollama model names
            "llama3.1:8b": "llama-3.1-8b-instant",
            "mistral:7b": "mixtral-8x7b-32768",
            "qwen2.5:7b": "llama-3.1-8b-instant",
        }
        groq_model = groq_model_map.get(model, "llama-3.1-8b-instant")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        completion = client.chat.completions.create(
            model=groq_model,
            messages=messages,
            temperature=temperature,
        )
        return completion.choices[0].message.content

    def _openrouter_chat(
        self,
        prompt: str,
        system: str,
        model: str,
        temperature: float,
        json_mode: bool,
    ) -> str:
        """Call OpenRouter's OpenAI-compatible chat completions endpoint."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        resp = requests.post(
            f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8501",
                "X-Title": "TalkingBI",
            },
            json=payload,
            timeout=120,
        )
        if not resp.ok:
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:400]
            logger.error(
                f"OpenRouter {resp.status_code} for model '{model}': {body}. "
                "Check PRIMARY_MODEL / CODE_MODEL in .env — visit openrouter.ai/models "
                "to find available free models."
            )
            # ── Groq fallback on rate-limit or server errors ──────────────────
            if resp.status_code in (429, 500, 502, 503, 504) and settings.GROQ_API_KEY:
                logger.warning(
                    f"OpenRouter {resp.status_code} — falling back to Groq for model '{model}'"
                )
                try:
                    return self._groq_chat(prompt, system, model, temperature)
                except Exception as groq_exc:
                    logger.error(f"Groq fallback also failed: {groq_exc}")
                    # Fall through to raise the original OpenRouter error
            # If JSON mode caused the error, retry without it
            if json_mode and resp.status_code in (400, 404, 422):
                payload.pop("response_format", None)
                retry = requests.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8501",
                        "X-Title": "TalkingBI",
                    },
                    json=payload,
                    timeout=120,
                )
                if retry.ok:
                    return retry.json()["choices"][0]["message"]["content"]
            resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def set_provider(self, provider: str) -> None:
        """Switch the active LLM provider at runtime."""
        self.provider = provider
        logger.info(f"LLM provider switched to: {provider}")

    def embed(self, text: str) -> list:
        """Generate embeddings using local sentence-transformers."""
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(settings.EMBED_MODEL)
        return model.encode(text).tolist()


llm = LLMClient()

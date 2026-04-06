import hashlib
import json
import requests
from pathlib import Path
from typing import Optional

from core.config import settings
from core.logger import logger
from core.exceptions import LLMError

# Fix 7 — LLM response cache directory
# Flat-file cache (one JSON per prompt+model hash) in data/cache/llm/.
# No external dependency — just pathlib + json, which are always available.
# Cache entries never expire automatically; delete data/cache/llm/ to reset.
_CACHE_DIR = Path("data/cache/llm")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(prompt: str, system: str, model: str) -> str:
    """
    MD5 of (model + system + prompt).

    System prompt is included in the key so schema-extraction prompts with
    different system contexts don't collide even when the user text is similar.
    """
    raw = f"{model}:{system}:{prompt}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class LLMClient:
    """
    Unified LLM client supporting Ollama, Groq, and OpenRouter.

    Fix 7 — chat() now supports an optional disk cache.
    Cache is enabled by default for structured/analytical calls
    (schema extraction, insight questions, chart type selection) and
    disabled for conversational replies where freshness matters.
    Pass use_cache=False to bypass for any call that should not be cached.
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
        use_cache: bool = True,   # Fix 7 — new parameter
    ) -> str:
        """
        Send a chat prompt to the configured LLM provider.

        Fix 7 — Cache behaviour:
          use_cache=True  (default): check disk cache before calling the LLM.
                                     Write result to cache on miss.
                                     Best for: schema analysis, insight questions,
                                     chart type selection, SQL generation templates.
          use_cache=False:           always call the LLM.
                                     Required for: conversational replies, anything
                                     time-sensitive or session-specific.

        Cache is keyed on (model, system, prompt) so the same analytical
        question on the same schema always hits the cache on the second run,
        even across server restarts.
        """
        model = model or self.primary

        # Fix 7 — cache lookup
        if use_cache:
            key = _cache_key(prompt, system, model)
            cache_file = _CACHE_DIR / f"{key}.json"
            if cache_file.exists():
                try:
                    cached = json.loads(cache_file.read_text(encoding="utf-8"))
                    logger.debug(f"LLM cache hit: {key[:8]}...")
                    return cached["response"]
                except Exception as e:
                    # Corrupted cache entry — just proceed with a real LLM call
                    logger.warning(f"LLM cache read failed ({key[:8]}): {e}")

        try:
            if self.provider == "ollama":
                response = self._ollama_chat(prompt, system, model, temperature, json_mode)
            elif self.provider == "groq":
                response = self._groq_chat(prompt, system, model, temperature, json_mode)
            elif self.provider == "openrouter":
                response = self._openrouter_chat(prompt, system, model, temperature, json_mode)
            else:
                raise LLMError(f"Unknown provider: {self.provider}")
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise LLMError(str(e)) from e

        # Fix 7 — write to cache on successful response
        if use_cache:
            try:
                cache_file.write_text(
                    json.dumps({"response": response}, ensure_ascii=False),
                    encoding="utf-8",
                )
                logger.debug(f"LLM cache written: {key[:8]}...")
            except Exception as e:
                # Cache write failure is non-fatal
                logger.warning(f"LLM cache write failed ({key[:8]}): {e}")

        return response

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
        self, prompt: str, system: str, model: str, temperature: float, json_mode: bool = False
    ) -> str:
        from groq import Groq, RateLimitError

        client = Groq(api_key=settings.GROQ_API_KEY)
        groq_model_map = {
            "nvidia/nemotron-3-super-120b-a12b:free": "llama-3.3-70b-versatile",
            "minimax/minimax-m2.5:free": "llama-3.3-70b-versatile",
            "meta-llama/llama-3.1-8b-instruct:free": "llama-3.1-8b-instant",
            "meta-llama/llama-3.1-70b-instruct:free": "llama-3.3-70b-versatile",
            "meta-llama/llama-4-maverick:free": "llama-3.3-70b-versatile",
            "meta-llama/llama-4-scout:free": "llama-3.1-8b-instant",
            "qwen/qwen-2.5-coder-7b-instruct:free": "llama-3.1-8b-instant",
            "mistralai/mistral-7b-instruct:free": "llama-3.1-8b-instant",
            "google/gemma-3-27b-it:free": "llama-3.3-70b-versatile",
            "llama3.1:8b": "llama-3.1-8b-instant",
            "mistral:7b": "llama-3.1-8b-instant",
            "qwen2.5:7b": "llama-3.1-8b-instant",
        }

        # Fallback models for each primary Groq model when rate limit is hit
        groq_fallback_map = {
            "llama-3.3-70b-versatile": ["llama-3.1-8b-instant", "llama3-70b-8192", "llama3-8b-8192"],
            "llama-3.1-8b-instant": ["llama-3.3-70b-versatile", "llama3-70b-8192", "llama3-8b-8192"],
            "llama3-70b-8192": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-8b-8192"],
            "llama3-8b-8192": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "llama3-70b-8192"],
        }

        groq_model = groq_model_map.get(model, "llama-3.1-8b-instant")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Try primary model and then fallbacks on rate limit error
        models_to_try = list(dict.fromkeys([groq_model] + groq_fallback_map.get(groq_model, [])))
        last_error: Optional[Exception] = None

        for attempt, try_model in enumerate(models_to_try):
            try:
                kwargs: dict = {
                    "model": try_model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                completion = client.chat.completions.create(**kwargs)
                
                # Log fallback success
                if attempt > 0:
                    logger.info(f"Groq rate limit fallback successful: {groq_model} → {try_model}")

                return completion.choices[0].message.content

            except RateLimitError as e:
                last_error = e
                if attempt < len(models_to_try) - 1:
                    logger.warning(
                        f"Groq rate limit hit for model '{try_model}' "
                        f"({attempt + 1}/{len(models_to_try)}). "
                        f"Falling back to '{models_to_try[attempt + 1]}'"
                    )
                else:
                    logger.error(
                        f"All Groq fallback models exhausted after rate limit hit. "
                        f"Last tried: {try_model}"
                    )
                    raise
            except Exception as e:
                last_error = e
                err = str(e).lower()
                is_model_decommissioned = (
                    "model_decommissioned" in err or "decommissioned" in err or "no longer supported" in err
                )
                is_model_missing = (
                    "model_not_found" in err or "not found" in err or "does not exist" in err
                )

                if (is_model_decommissioned or is_model_missing) and attempt < len(models_to_try) - 1:
                    logger.warning(
                        f"Groq fallback model '{try_model}' failed: {e}. Trying next fallback..."
                    )
                    continue

                # For non-model errors, keep original behavior and fail fast.
                raise

        if settings.OPENROUTER_API_KEY:
            logger.warning(
                f"All Groq fallback models failed for '{model}'. Falling back to OpenRouter."
            )
            try:
                return self._openrouter_chat(prompt, system, model, temperature, json_mode)
            except Exception as openrouter_exc:
                logger.error(f"OpenRouter fallback also failed: {openrouter_exc}")
                raise

        raise LLMError(str(last_error) if last_error else "Groq fallback models exhausted")

    def _openrouter_chat(
        self,
        prompt: str,
        system: str,
        model: str,
        temperature: float,
        json_mode: bool,
    ) -> str:
        """Call OpenRouter's OpenAI-compatible chat completions endpoint with fallback support."""
        
        # Fallback models for each primary model when rate limit is hit
        openrouter_fallback_map = {
            "meta-llama/llama-3.1-8b-instruct:free": [
                "qwen/qwen3.6-plus:free",
                "stepfun/step-3.5-flash:free",
                "arcee-ai/trinity-large-preview:free",
                "openai/gpt-oss-120b:free",
                "nousresearch/hermes-3-llama-3.1-405b:free",
            ],
            "meta-llama/llama-3.1-70b-instruct:free": [
                "nousresearch/hermes-3-llama-3.1-405b:free",
                "openai/gpt-oss-120b:free",
                "arcee-ai/trinity-large-preview:free",
                "stepfun/step-3.5-flash:free",
                "qwen/qwen3.6-plus:free",
            ],
            "qwen/qwen-2.5-coder-7b-instruct:free": [
                "stepfun/step-3.5-flash:free",
                "arcee-ai/trinity-large-preview:free",
                "qwen/qwen3.6-plus:free",
                "openai/gpt-oss-120b:free",
                "nousresearch/hermes-3-llama-3.1-405b:free",
            ],
            "mistralai/mistral-7b-instruct:free": [
                "arcee-ai/trinity-large-preview:free",
                "qwen/qwen3.6-plus:free",
                "stepfun/step-3.5-flash:free",
                "nousresearch/hermes-3-llama-3.1-405b:free",
                "openai/gpt-oss-120b:free",
            ],
        }
        
        # Default fallback chain for unknown models
        default_fallback = [
            "qwen/qwen3.6-plus:free",
            "stepfun/step-3.5-flash:free",
            "arcee-ai/trinity-large-preview:free",
            "openai/gpt-oss-120b:free",
            "nousresearch/hermes-3-llama-3.1-405b:free",
        ]
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        # Build list of models to try (primary + fallbacks)
        models_to_try = [model] + openrouter_fallback_map.get(model, default_fallback)
        
        for attempt, try_model in enumerate(models_to_try):
            payload: dict = {
                "model": try_model,
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
            
            if resp.ok:
                # Log fallback success
                if attempt > 0:
                    logger.info(f"OpenRouter rate limit fallback successful: {model} → {try_model}")
                return resp.json()["choices"][0]["message"]["content"]
            
            # Check if this is a rate limit or retriable error
            is_retriable = resp.status_code in (429, 500, 502, 503, 504)
            
            if is_retriable and attempt < len(models_to_try) - 1:
                try:
                    err_body = resp.json()
                except Exception:
                    err_body = resp.text[:200]
                logger.warning(
                    f"OpenRouter {resp.status_code} for model '{try_model}' "
                    f"({attempt + 1}/{len(models_to_try)}). "
                    f"Falling back to '{models_to_try[attempt + 1]}'"
                )
                continue
            
            # Handle json_mode fallback for unsupported models
            if json_mode and resp.status_code in (400, 404, 422) and attempt < len(models_to_try) - 1:
                logger.warning(
                    f"OpenRouter {resp.status_code} for model '{try_model}' with json_mode. "
                    f"Falling back to '{models_to_try[attempt + 1]}'"
                )
                continue
            
            # Try json_mode retry without response_format for this model
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
                    # Log fallback success
                    if attempt > 0:
                        logger.info(f"OpenRouter fallback successful (json_mode retry): {model} → {try_model}")
                    return retry.json()["choices"][0]["message"]["content"]
            
            # If this is the last model or a non-retriable error, raise
            if attempt == len(models_to_try) - 1:
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text[:400]
                logger.error(
                    f"All OpenRouter fallback models exhausted. "
                    f"Last error ({resp.status_code}) for model '{try_model}': {body}. "
                    "Check PRIMARY_MODEL / CODE_MODEL in .env — visit openrouter.ai/models "
                    "to find available free models."
                )
                resp.raise_for_status()
        
        raise LLMError("All OpenRouter fallback models exhausted")

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
"""
Embedding wrapper for TalkingBI vector store.
"""
from __future__ import annotations

from typing import List

import numpy as np

from core.config import settings
from core.logger import logger


class Embedder:
    """Wraps sentence-transformers for text embedding."""

    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
                logger.info(f"Embedder loaded: {settings.EMBEDDING_MODEL}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise

    def embed(self, text: str) -> List[float]:
        """Embed a single text string."""
        self._load()
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts."""
        self._load()
        vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=32)
        return vecs.tolist()

    def similarity(self, a: List[float], b: List[float]) -> float:
        """Cosine similarity between two embedding vectors."""
        va = np.array(a)
        vb = np.array(b)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        if denom == 0:
            return 0.0
        return float(np.dot(va, vb) / denom)


embedder = Embedder()

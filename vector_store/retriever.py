"""
Retrieval interface for TalkingBI vector store.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from core.config import settings
from core.logger import logger
from vector_store.embedder import embedder


class VectorRetriever:
    """Retrieves semantically similar documents from a ChromaDB collection."""

    def __init__(self, collection_name: str):
        self._collection_name = collection_name[:63]
        self._client = chromadb.PersistentClient(
            path=str(settings.CHROMA_PERSIST_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None):
        """Add or update a document in the collection."""
        vec = embedder.embed(text)
        self._collection.upsert(
            ids=[doc_id],
            embeddings=[vec],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def add_batch(self, docs: List[Dict[str, Any]]):
        """Add a batch of documents. Each element: {id, text, metadata}."""
        ids = [d["id"] for d in docs]
        texts = [d["text"] for d in docs]
        metadatas = [d.get("metadata", {}) for d in docs]
        vecs = embedder.embed_batch(texts)
        self._collection.upsert(
            ids=ids,
            embeddings=vecs,
            documents=texts,
            metadatas=metadatas,
        )

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve top-k most similar documents to the query."""
        q_vec = embedder.embed(query)
        results = self._collection.query(
            query_embeddings=[q_vec],
            n_results=min(top_k, self._collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )
        output = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            output.append({"text": doc, "metadata": meta, "distance": dist})
        return output

    def count(self) -> int:
        return self._collection.count()

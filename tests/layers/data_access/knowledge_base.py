import json
import chromadb
from sentence_transformers import SentenceTransformer
from core.config import settings
from core.logger import logger
from layers.data_access.explorer import Triplet


class TripletKnowledgeBase:
    """
    Stores and retrieves (Schema, SQL, NL) triplets using ChromaDB.
    Enables semantic similarity search during SQL generation.
    """

    def __init__(self, db_name: str):
        self.db_name = db_name
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        collection_name = f"triplets_{db_name}"[:63]  # ChromaDB name limit
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.embedder = SentenceTransformer(settings.EMBED_MODEL)

    def add_triplets(self, triplets: list):
        """Embed and store triplets in ChromaDB."""
        if not triplets:
            return

        ids, embeddings, documents, metadatas = [], [], [], []
        for i, t in enumerate(triplets):
            emb = self.embedder.encode(t.sql_query).tolist()
            ids.append(f"{self.db_name}_triplet_{i}_{abs(hash(t.sql_query)) % 1000000}")
            embeddings.append(emb)
            documents.append(t.nl_description)
            metadatas.append(
                {
                    "sql": t.sql_query,
                    "tables": json.dumps(t.tables_used),
                    "schema": json.dumps(t.schema_fragment),
                }
            )

        # Upsert to avoid duplicate key issues
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(f"Stored {len(triplets)} triplets for DB: {self.db_name}")

    def retrieve(self, query: str, top_k: int = None) -> list:
        """Retrieve most relevant triplets for a given NL query."""
        top_k = top_k or settings.TOP_K
        query_emb = self.embedder.encode(query).tolist()
        count = self.collection.count()
        if count == 0:
            return []

        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=min(top_k, count),
        )

        triplets = []
        if results and results["metadatas"]:
            for meta, doc in zip(results["metadatas"][0], results["documents"][0]):
                triplets.append(
                    {
                        "sql": meta["sql"],
                        "description": doc,
                        "tables": json.loads(meta["tables"]),
                        "schema": json.loads(meta["schema"]),
                    }
                )
        return triplets

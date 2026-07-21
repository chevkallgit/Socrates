"""ChromaRepository — Repository pattern over ChromaDB.

This class is the ONLY thing in the app that touches the chromadb client:
the Single Owner. Services and routes depend on this abstraction, never on
chromadb directly, so the vector store could later be swapped (pgvector,
Qdrant, ...) without changing a single route handler.
"""

import chromadb

from schemas import Chunk


class ChromaRepository:
    def __init__(self, host: str, port: int, collection_name: str) -> None:
        # Chroma is running as a server (see PLANNING.md), so use HttpClient
        # rather than a persistent/embedded client.
        self._client = chromadb.HttpClient(host=host, port=port)
        self._collection = self._client.get_collection(collection_name)

    def search(self, embedding: list[float], k: int) -> list[Chunk]:
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        return self._to_chunks(result)

    @staticmethod
    def _to_chunks(result: dict) -> list[Chunk]:
        # Chroma returns parallel lists nested one level deep (one inner list
        # per submitted query). We submit a single query, so index [0].
        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]
        return [
            Chunk(id=cid, text=doc, metadata=meta or {}, distance=dist)
            for cid, doc, meta, dist in zip(ids, documents, metadatas, distances)
        ]

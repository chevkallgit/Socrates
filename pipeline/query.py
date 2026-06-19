"""
query.py
--------
Semantic search against the ChromaDB vector database.

Given a natural language question, finds the most relevant chunks from the
textbook. This is the retrieval half of a RAG (Retrieval-Augmented Generation)
pipeline — later the Go API will call something like this, then pass the
results to an LLM to generate a grounded answer.

Usage:
    python query.py --question "What is a write-ahead log?"
    python query.py --question "How does Kafka handle replication?" --top 5

Dependencies:
    pip install chromadb sentence-transformers
"""

import argparse

import chromadb
from chromadb.utils import embedding_functions

from embed import COLLECTION_NAME, EMBEDDING_MODEL


# ---------------------------------------------------------------------------
# Query the vector database
# ---------------------------------------------------------------------------


def search(db_path: str, question: str, top_k: int = 3) -> list[dict]:
    """
    Searches the Chroma collection for chunks semantically similar to
    the given question.

    How it works:
      1. The question is converted to an embedding vector using the same model
         used during ingestion — same model = same embedding space.
      2. Chroma computes cosine similarity between the question embedding and
         every stored chunk embedding.
      3. The top_k most similar chunks are returned.

    Cosine similarity measures the angle between two vectors (ignoring magnitude).
    A score close to 1.0 means very similar; close to 0 means unrelated.

    Returns a list of dicts with: content, chapter, section, page, score
    """
    client = chromadb.PersistentClient(path=db_path)

    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

    collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
    )

    results = collection.query(
        query_texts=[question],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    # Chroma returns results nested in lists (supports batch queries).
    # Since we query one question at a time, we unpack the first element.
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    # Convert cosine distance → similarity score (distance = 1 - similarity)
    hits = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        hits.append({
            "content": doc,
            "chapter": meta.get("chapter_title", ""),
            "section": meta.get("section_title", ""),
            "page": meta.get("page", -1),
            "score": round(1 - dist, 4),
        })

    return hits


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search the textbook vector database."
    )
    parser.add_argument("--question", required=True, help="Natural language question")
    parser.add_argument("--db", default="./chroma_db", help="ChromaDB directory")
    parser.add_argument("--top", type=int, default=3, help="Number of results to return")

    args = parser.parse_args()

    print(f'\nSearching for: "{args.question}"\n')
    hits = search(args.db, args.question, top_k=args.top)

    for i, hit in enumerate(hits, start=1):
        print(f"--- Result {i} (score: {hit['score']}) ---")
        print(f"Chapter: {hit['chapter']}")
        if hit["section"]:
            print(f"Section: {hit['section']}")
        print(f"Page: {hit['page']}")
        print(f"Content: {hit['content'][:300]}{'...' if len(hit['content']) > 300 else ''}")
        print()


if __name__ == "__main__":
    main()

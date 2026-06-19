"""
embed.py
--------
Loads extracted chunks into a ChromaDB vector database.

What is a vector database?
  A vector database stores text as *embeddings* — lists of ~384 numbers that
  capture the semantic meaning of the text. Two chunks about similar topics
  will have embeddings that are "close" in this high-dimensional space.

  This lets us do semantic search: "What is a write-ahead log?" finds chunks
  about durability and crash recovery even if they never use those exact words.

  Flow:
    text chunk → embedding model → [0.12, -0.34, 0.87, ...] → stored in Chroma
    query text  → embedding model → [0.11, -0.31, 0.90, ...] → compared to stored
    → returns N most similar chunks

Usage:
    python embed.py --input chunks.json
    python embed.py --input chunks.json --db ./chroma_db --reset

Dependencies:
    pip install chromadb sentence-transformers
"""

import argparse
import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The embedding model. "all-MiniLM-L6-v2" is a great default:
#   - Small and fast (runs on CPU, no GPU needed)
#   - Produces 384-dimensional embeddings
#   - Good semantic understanding for English prose
# It downloads automatically on first run (~90MB, cached after that).
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Chroma collection name — think of this like a table in a SQL database.
# We'll have one collection per textbook.
COLLECTION_NAME = "textbook_chunks"

# Chroma batch size — how many chunks to upsert at once.
# Too large and you'll hit memory limits; too small and it's slow.
BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# Load chunks from extract.py output
# ---------------------------------------------------------------------------


def load_chunks(input_path: str) -> tuple[list[dict], list[dict]]:
    """
    Reads the JSON file produced by extract.py.
    Returns (nodes, chunks) as plain dicts.
    """
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    nodes = data["nodes"]
    chunks = data["chunks"]

    print(f"Loaded {len(nodes)} nodes and {len(chunks)} chunks from {input_path}")
    return nodes, chunks


# ---------------------------------------------------------------------------
# Build a node lookup so we can enrich chunks with chapter/section titles
# ---------------------------------------------------------------------------


def build_node_lookup(nodes: list[dict]) -> dict[int, dict]:
    """
    Turns the nodes list into a dict keyed by node ID.
    This lets us do O(1) lookups when enriching each chunk's metadata.

    Dict comprehensions work like list comprehensions but produce dicts:
        {key_expr: value_expr for item in iterable}
    """
    return {node["id"]: node for node in nodes}


# ---------------------------------------------------------------------------
# Initialise ChromaDB
# ---------------------------------------------------------------------------


def get_chroma_collection(
    db_path: str,
    collection_name: str,
    reset: bool = False,
) -> chromadb.Collection:
    """
    Creates (or connects to) a persistent ChromaDB instance and returns
    the collection we'll store chunks in.

    ChromaDB concepts:
      - Client:     the database itself, stored on disk at db_path
      - Collection: like a table — holds documents, embeddings, and metadata
      - Document:   the raw text of a chunk
      - Embedding:  the vector representation (auto-generated)
      - Metadata:   extra fields we want to filter on (chapter, page, etc.)
      - ID:         unique string identifier for each document

    We use SentenceTransformerEmbeddingFunction so Chroma automatically
    generates embeddings when we add documents — we never call the model
    directly. Chroma handles batching and caching internally.
    """
    # PersistentClient stores the DB on disk — data survives between runs.
    client = chromadb.PersistentClient(path=db_path)

    if reset:
        # delete_collection silently succeeds if it doesn't exist
        try:
            client.delete_collection(collection_name)
            print(f"  Deleted existing collection '{collection_name}'")
        except Exception:
            pass

    # SentenceTransformerEmbeddingFunction wraps the model so Chroma can
    # call it automatically when adding or querying documents.
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

    # get_or_create_collection is idempotent — safe to call on every run.
    # If the collection already exists, we get it back unchanged.
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},  # use cosine similarity for text
    )

    return collection


# ---------------------------------------------------------------------------
# Load chunks into Chroma
# ---------------------------------------------------------------------------


def embed_chunks(
    collection: chromadb.Collection,
    chunks: list[dict],
    node_lookup: dict[int, dict],
) -> None:
    """
    Upserts all chunks into the Chroma collection.

    Upsert = insert or update. If a chunk with the same ID already exists,
    it's overwritten. This makes the script safely re-runnable.

    We batch the upserts to avoid memory issues with large books.
    A 500-page textbook might have 3,000+ chunks — doing them all at once
    would load thousands of embeddings into memory simultaneously.

    Metadata we store per chunk:
      - node_id:       FK to the parent node
      - node_type:     "chapter", "section", or "front_matter"
      - chapter_title: title of the containing chapter (for display)
      - section_title: title of the containing section (for display)
      - page:          page number (for citations)
      - order_index:   position within the parent node (for re-ordering)
    """
    total = len(chunks)
    loaded = 0

    # Process in batches
    for batch_start in range(0, total, BATCH_SIZE):
        batch = chunks[batch_start : batch_start + BATCH_SIZE]

        ids = []
        documents = []
        metadatas = []

        for chunk in batch:
            node_id = chunk["node_id"]
            node = node_lookup.get(node_id, {}) if node_id else {}

            # Walk up the tree to find chapter title for this chunk.
            # If this chunk's parent is a section, we need the section's parent
            # to get the chapter title.
            chapter_title = ""
            section_title = ""

            if node:
                if node["type"] == "chapter":
                    chapter_title = node["title"]
                elif node["type"] == "section":
                    section_title = node["title"]
                    parent = node_lookup.get(node["parent_id"], {})
                    chapter_title = parent.get("title", "")

            ids.append(f"chunk_{batch_start + len(ids)}")
            documents.append(chunk["content"])
            metadatas.append({
                "node_id": node_id or -1,
                "node_type": node.get("type", "unknown"),
                "chapter_title": chapter_title,
                "section_title": section_title,
                "page": chunk["page"],
                "order_index": chunk["order_index"],
            })

        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        loaded += len(batch)
        print(f"  Loaded {loaded}/{total} chunks...", end="\r")

    print(f"\n  Done. {total} chunks in collection '{collection.name}'")
    print(f"  Total documents in DB: {collection.count()}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def embed(input_path: str, db_path: str, reset: bool) -> None:
    print(f"Loading from: {input_path}")
    nodes, chunks = load_chunks(input_path)

    node_lookup = build_node_lookup(nodes)

    print(f"\nInitialising ChromaDB at: {db_path}")
    collection = get_chroma_collection(db_path, COLLECTION_NAME, reset=reset)

    print(f"\nEmbedding and loading chunks (model: {EMBEDDING_MODEL})...")
    print("  First run downloads the model (~90MB). This is cached after that.\n")

    embed_chunks(collection, chunks, node_lookup)

    print("\n✓ Vector database ready.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed extracted chunks into a ChromaDB vector database."
    )
    parser.add_argument("--input", default="chunks.json",
                        help="Path to chunks.json from extract.py")
    parser.add_argument("--db", default="./chroma_db",
                        help="Directory to store the ChromaDB files")
    parser.add_argument("--reset", action="store_true",
                        help="Delete and recreate the collection (re-embed everything)")

    args = parser.parse_args()
    embed(args.input, args.db, args.reset)


if __name__ == "__main__":
    main()

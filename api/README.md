# Socrates API

FastAPI read layer over the textbook vector store. This process is the
**Single Owner of ChromaDB** — it loads the embedding model, embeds incoming
queries, retrieves chunks, and (for `/ask`) augments a Claude call with them.

## Layout

| File             | Role                                                        |
|------------------|-------------------------------------------------------------|
| `config.py`      | Typed settings (pydantic-settings), env-overridable         |
| `schemas.py`     | Pydantic DTOs — the API contract                            |
| `embedder.py`    | `Embedder` — Single Owner of the sentence-transformers model |
| `repository.py`  | `ChromaRepository` — Repository pattern over ChromaDB       |
| `rag.py`         | `RagService` — Service layer (embed → retrieve → generate)  |
| `main.py`        | App factory, lifespan composition root, DI, routes          |

## Run

```bash
pip install -r requirements.txt

# ChromaDB must already be serving on the configured host/port (default 8001)
export ANTHROPIC_API_KEY=sk-ant-...        # only needed for /ask
uvicorn main:app --reload
```

Interactive docs: http://localhost:8000/docs

## Config (env vars, all optional except the key for /ask)

| Variable             | Default            |
|----------------------|--------------------|
| `CHROMA_HOST`        | `localhost`        |
| `CHROMA_PORT`        | `8001`             |
| `COLLECTION_NAME`    | `textbook_chunks`  |
| `EMBEDDING_MODEL`    | `all-MiniLM-L6-v2` |
| `TOP_K`              | `5`                |
| `ANTHROPIC_API_KEY`  | *(empty)*          |
| `ANSWER_MODEL`       | `claude-sonnet-4-6`|
| `MAX_TOKENS`         | `1024`             |

## Endpoints

`POST /search` — pure semantic retrieval.
```json
{ "query": "what is a write-ahead log", "k": 5 }
```

`POST /ask` — RAG: retrieve, then answer grounded in the chunks, with sources.
```json
{ "question": "Why use a write-ahead log?", "k": 5 }
```

`GET /health` — liveness probe.

## Notes

- `EMBEDDING_MODEL` **must** match what the pipeline used to embed the chunks,
  or query and document vectors won't share a space.
- Queries pass `query_embeddings` (embedding done here in Python) rather than
  `query_texts`, matching how `query.py` already works against the collection.

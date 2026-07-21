# Socrates — Planning & Architecture

Source-of-truth document for architecture decisions, the patterns in play, and open questions. This is the doc to read before making a structural change.

---

## What Socrates is

An interactive tutor for technical textbooks. Today it does retrieval-augmented Q&A over a book (currently *Designing Data-Intensive Applications*). The longer-term product adds audiobook playback, quizzing, and conversational follow-ups. This repo doubles as a portfolio piece (public, DDIA as the test book) and the foundation for a future product (private fork, user-uploaded PDFs).

---

## System shape

```
pipeline/   Python   — runs once per book: extract → chunk → embed → load into ChromaDB
api/        FastAPI  — runtime: embed query → retrieve → (for /ask) generate with Claude
mobile/     RN/Expo  — user-facing app (planned)
```

At runtime there are two processes: a **ChromaDB server** (serving the data the pipeline built, from `pipeline/chroma_db`) and the **FastAPI app** that reads from it.

---

## Key decision: Go dropped in favor of FastAPI

The API layer was originally going to be Go. It's now Python/FastAPI. Reasoning:

- The Go service was going to talk to ChromaDB over REST anyway — the Go Chroma client was unreliable on Windows — so "Go owns Chroma" was already Go-over-HTTP-to-Chroma.
- Python already owns the embedding model (the pipeline uses sentence-transformers). Putting the API in Python means the **same process that creates embeddings also serves them** — no second language, no duplicated model, no cross-language hop.
- This makes FastAPI the **Single Owner of ChromaDB**: one runtime, one owner of that store.

Net effect: one fewer service and one fewer language, with the single-owner property preserved. Simpler is the point.

---

## Patterns in the API

- **Single Owner** — one service owns one data store. FastAPI is the sole owner of ChromaDB; nothing else queries it directly.
- **Repository pattern** — `ChromaRepository` is the only code that touches the `chromadb` client. Services depend on the repository, not the DB, so the store could be swapped (pgvector, Qdrant) without touching routes.
- **Service layer** — `RagService` orchestrates embed → retrieve → generate, keeping business logic out of the HTTP handlers.
- **Dependency Injection** — FastAPI `Depends` + the `lifespan` composition root build the heavy singletons (embedding model, Chroma client, Anthropic client) once at startup and hand them to routes.
- **DTOs** — Pydantic models are the API contract and drive the auto-generated OpenAPI docs at `/docs`.

### API file layout

Flat inside `api/` so `uvicorn main:app` (launched from `api/`) resolves the `from config import ...` style imports.

| File            | Role                                              |
|-----------------|---------------------------------------------------|
| `config.py`     | Typed settings (pydantic-settings), env/.env      |
| `schemas.py`    | Pydantic DTOs — the API contract                  |
| `embedder.py`   | `Embedder` — single owner of the MiniLM model     |
| `repository.py` | `ChromaRepository` — repository over ChromaDB     |
| `rag.py`        | `RagService` — embed → retrieve → generate        |
| `main.py`       | App factory, lifespan, DI, routes                 |

---

## Runtime data flow

`POST /search`: embed the query (MiniLM) → `ChromaRepository.search` returns top-k chunks.

`POST /ask`: same retrieval → format retrieved chunks as numbered context → Claude answers **only** from that context (system prompt instructs it to say so when the context is insufficient rather than guess) → return answer + the source chunks.

Consistency requirement: the API must embed queries with the **same model** the pipeline used on the chunks (`all-MiniLM-L6-v2`), or query and document vectors don't share a space. Queries pass `query_embeddings` (embedding done in Python), matching how `query.py` works — not `query_texts`.

---

## Current state

- Pipeline is mature: `extract.py`, `embed.py`, `query.py` built and verified. Paragraph-level chunking, front matter / running headers / glossary / index filtered out.
- FastAPI app built and running end to end: `/search`, `/ask`, `/health` all live. Verified against the real DDIA collection.
- Chunk metadata keys as stored by the pipeline: `chapter_title`, `section_title`, `page`, `node_id`, `node_type`, `order_index`.

---

## Open questions / next up

- **Chunking quality.** Retrieval currently matches on surface wording (small MiniLM model), so passages that merely *mention* a term compete with the section that *defines* it. Fixed-size-with-overlap chunking is the flagged refinement. Worth revisiting before adding more books.
- **Citation labels.** `RagService._format_context` should read `section_title` / `chapter_title` (the actual stored keys) so the `[n]` labels aren't blank.
- **Frontend.** Next.js against these endpoints.
- **Generalization.** Beyond DDIA to user-uploaded PDFs (private fork / product path).
- **Mobile.** React Native app (longer-term).

---

## Future production data architecture

Polyglot persistence once this leaves local-first:

- **Object storage** — the source PDFs.
- **Postgres** — users, ownership, book metadata.
- **ChromaDB (or managed vector store)** — vectors, at scale.

Each store owned by the service responsible for it, preserving the single-owner discipline as the system grows.

---

## Conventions

- Git: `main` / `dev` / `feature` branches, Conventional Commits, GitHub Actions CI. Public repo: `chevkallgit/Socrates`.
- Architecture stays as simple as the problem requires — no service is added without a reason the current design can't meet.

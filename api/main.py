"""FastAPI entrypoint.

Wires everything together. The `lifespan` block is the composition root: the
heavy singletons (embedding model, Chroma connection, Anthropic client) are
built ONCE at startup and stashed on app.state. Route handlers receive the
RagService via Dependency Injection, so they never construct collaborators
themselves and stay trivially testable.

Run:  uvicorn main:app --reload
Docs: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from anthropic import Anthropic
from fastapi import Depends, FastAPI, HTTPException, Request

from config import Settings, get_settings
from embedder import Embedder
from rag import RagService
from repository import ChromaRepository
from schemas import AskRequest, AskResponse, SearchRequest, SearchResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    embedder = Embedder(settings.embedding_model)
    repository = ChromaRepository(
        host=settings.chroma_host,
        port=settings.chroma_port,
        collection_name=settings.collection_name,
    )
    client = Anthropic(api_key=settings.anthropic_api_key or None)
    app.state.rag = RagService(
        embedder=embedder,
        repository=repository,
        client=client,
        model=settings.answer_model,
        max_tokens=settings.max_tokens,
    )
    yield  # app serves requests here; clients are GC'd on shutdown


app = FastAPI(title="Socrates API", version="0.1.0", lifespan=lifespan)


# --- Dependency providers -------------------------------------------------
def get_rag(request: Request) -> RagService:
    return request.app.state.rag


# --- Routes ---------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/search", response_model=SearchResponse)
def search(
    body: SearchRequest,
    rag: RagService = Depends(get_rag),
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    k = body.k or settings.top_k
    results = rag.search(body.query, k)
    return SearchResponse(query=body.query, results=results)


@app.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    rag: RagService = Depends(get_rag),
    settings: Settings = Depends(get_settings),
) -> AskResponse:
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
    k = body.k or settings.top_k
    return rag.ask(body.question, k)

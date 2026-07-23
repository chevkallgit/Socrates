"""Data Transfer Objects (DTOs).

These Pydantic models ARE the API contract. FastAPI uses them to validate
incoming JSON, serialize outgoing JSON, and auto-generate the OpenAPI schema
at /docs. Keeping them in one place means the shape of the API is readable
without grepping the route handlers.
"""

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """One retrieved passage from the textbook."""

    id: str
    text: str
    metadata: dict = Field(default_factory=dict)
    distance: float | None = None  # raw Chroma distance; lower = closer


class SearchRequest(BaseModel):
    query: str
    k: int | None = None  # falls back to settings.top_k when omitted


class SearchResponse(BaseModel):
    query: str
    results: list[Chunk]


class AskRequest(BaseModel):
    question: str
    k: int | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[Chunk]  # what the answer was grounded in, for transparency

class Section(BaseModel):
    title: str
    page: int | None = None


class Chapter(BaseModel):
    title: str
    sections: list[Section]


class ChaptersResponse(BaseModel):
    chapters: list[Chapter]
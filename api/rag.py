"""RagService — the Service layer.

Orchestrates the RAG flow: embed -> retrieve (Repository) -> augment ->
generate (Claude). Keeping this out of the route handlers means the HTTP
layer stays thin and this logic is unit-testable without spinning up a server.
"""

from anthropic import Anthropic

from embedder import Embedder
from repository import ChromaRepository
from schemas import AskResponse, Chunk

SYSTEM_PROMPT = (
    "You are Socrates, a study assistant answering questions about a textbook. "
    "Answer ONLY from the provided context passages. If the context does not "
    "contain the answer, say so plainly rather than guessing. When you use a "
    "passage, cite it by its [n] number."
)


class RagService:
    def __init__(
        self,
        embedder: Embedder,
        repository: ChromaRepository,
        client: Anthropic,
        model: str,
        max_tokens: int,
    ) -> None:
        self._embedder = embedder
        self._repository = repository
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def search(self, query: str, k: int) -> list[Chunk]:
        embedding = self._embedder.embed(query)
        return self._repository.search(embedding, k)

    def ask(self, question: str, k: int) -> AskResponse:
        # Retrieval-Augmented Generation: retrieve first, then condition the
        # model on what we found instead of trusting its parametric memory.
        sources = self.search(question, k)
        context = self._format_context(sources)

        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Context passages:\n\n{context}\n\n"
                        f"Question: {question}"
                    ),
                }
            ],
        )

        answer = "".join(
            block.text for block in message.content if block.type == "text"
        )
        return AskResponse(question=question, answer=answer, sources=sources)

    @staticmethod
    def _format_context(chunks: list[Chunk]) -> str:
        blocks = []
        for i, chunk in enumerate(chunks, start=1):
            # Surface any structural location the pipeline stored, if present.
            location = (
                chunk.metadata.get("section")
                or chunk.metadata.get("chapter")
                or chunk.metadata.get("title")
                or ""
            )
            header = f"[{i}] {location}".rstrip()
            blocks.append(f"{header}\n{chunk.text}")
        return "\n\n".join(blocks)

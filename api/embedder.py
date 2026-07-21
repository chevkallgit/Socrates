"""Embedder — Single Owner of the sentence-transformers model.

The model is loaded once at startup (it's the expensive part) and shared
across every request. Embedding the query with the SAME model the pipeline
used on the chunks is the whole reason vector search returns relevant text.
"""

from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        # No normalization, to mirror the pipeline's default encode() — keep
        # this consistent with however the stored chunk vectors were produced.
        vector = self._model.encode(text)
        return vector.tolist()

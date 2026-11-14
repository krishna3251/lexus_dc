"""Lexical retrieval needs no external embedding provider or model download."""


class LexicalOnlyEmbeddingService:
    """Keep the existing RAG interface while disabling external embeddings."""

    model = "lexical-only"
    dimensions = 0
    available = False

    async def embed_query(self, query: str) -> list[float]:
        raise RuntimeError("External embeddings are disabled; use lexical retrieval")

    async def embed_document(self, title: str, text: str) -> list[float]:
        raise RuntimeError("External embeddings are disabled; use lexical retrieval")

    async def close(self) -> None:
        return None

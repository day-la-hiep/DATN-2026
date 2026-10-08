"""Embedding LOCAL dùng chung"""
from typing import Any


class EmbeddingClient:
    def __init__(self) -> None:
        self._model: Any = None

    @property
    def model(self) -> Any:
        if self._model is None:
            from agent.embeddings import LocalEmbeddings

            self._model = LocalEmbeddings()
        return self._model

    def embed(self, texts: list[str]) -> tuple[list[list[float]], int, str]:
        """Trả (vector từng văn bản, số chiều, tên model)."""
        from agent.embeddings import EMBEDDING_DIM, EMBEDDING_MODEL_NAME

        return self.model.embed_documents(texts), EMBEDDING_DIM, EMBEDDING_MODEL_NAME

"""Embedding LOCAL dùng chung: class `EmbeddingClient` (sentence-transformers qua `agent/embeddings.py`, 384 chiều). Nạp mô hình rất nặng nên
lười (lần `embed` đầu tiên). Chạy ĐỒNG BỘ. Instance do `app/api/deps.py` tạo; test thay bằng đối tượng có cùng phương thức `embed`."""
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

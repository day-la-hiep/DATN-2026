"""Lớp truy xuất vector tùy chọn; không làm hỏng chatbot nếu index chưa tồn tại."""

from __future__ import annotations

import json
from pathlib import Path

from .retrieval import Match


class SemanticRetriever:
    def __init__(self, index_dir: Path) -> None:
        self.available = False
        self.reason = "Semantic index chưa được tạo."
        self._index = None
        self._model = None
        self._chunks: list[dict] = []
        index_path = index_dir / "conditions.faiss"
        chunks_path = index_dir / "chunks.json"
        if not index_path.exists() or not chunks_path.exists():
            return
        try:
            import faiss
            from sentence_transformers import SentenceTransformer

            payload = json.loads(chunks_path.read_text(encoding="utf-8"))
            self._index = faiss.read_index(str(index_path))
            self._chunks = payload.get("chunks", [])
            # API chỉ nạp model đã cache khi khởi động: không tạo network request ngầm.
            model_path_str = payload.get("model_path") or payload.get("model_name", "")
            model_path = (index_dir / model_path_str).resolve()
            self._model = SentenceTransformer(
                str(model_path),
                local_files_only=True,
                tokenizer_kwargs={"fix_mistral_regex": True},
            )
            self.available = True
            self.reason = ""
        except Exception as error:  # Có fallback keyword thay vì làm API dừng.
            self.reason = f"Không tải được semantic index: {type(error).__name__}"

    def search(self, message: str, limit: int = 3, chunk_type: str | None = None) -> list[Match]:
        if not self.available:
            return []
        import numpy as np

        vector = self._model.encode([message], normalize_embeddings=True)
        fetch_limit = limit * 5 if chunk_type else limit
        fetch_limit = min(fetch_limit, len(self._chunks))
        if fetch_limit <= 0:
            return []

        scores, indexes = self._index.search(np.asarray(vector, dtype="float32"), fetch_limit)
        matches: list[Match] = []
        for score, position in zip(scores[0], indexes[0]):
            if position < 0:
                continue
            chunk = self._chunks[int(position)]
            if chunk_type and chunk.get("chunk_type") != chunk_type:
                continue
            # Lưu toàn bộ chunk để tools.py đọc được text/chunk_type/source_label.
            # engine.py sẽ dùng chunk["disease"] để lấy disease object.
            matches.append(
                Match(
                    disease=chunk,
                    score=float(score),
                    matched_features=["semantic_match"],
                )
            )
            if len(matches) >= limit:
                break
        return matches

"""Embedding LOCAL (sentence-transformers, chạy CPU, không gọi API ngoài) — dùng chung
cho long-term memory (`agent/tools/memory.py`), `hybrid_retrieval` (`agent/tools/hybrid_retrieval/`) và pipeline index sách. Thay cho `GoogleGenerativeAIEmbeddings`
trước đây (bắt buộc `GOOGLE_API_KEY`) — cùng lúc `AGENT_MODEL` chuyển sang OpenRouter/
Gemma (`agent/llm.py`), project không còn phụ thuộc Google ở bất kỳ đâu.

Model đa ngôn ngữ (hỗ trợ tiếng Việt) — cùng lựa chọn với prototype cũ
(`knowledge_base/src/semantic.py`). Tải về ~470MB lần chạy đầu tiên (cache tại
`~/.cache/huggingface`), các lần sau load từ cache, không cần mạng.
"""
import app.config.settings  # noqa: F401  # phải đứng TRƯỚC sentence_transformers: nạp `.env` (HF_HUB_OFFLINE...) trước khi huggingface_hub đọc biến môi trường
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


class LocalEmbeddings(Embeddings):
    """Chỉ cài sync (`sentence-transformers` không có async) — lớp cơ sở
    `langchain_core.embeddings.Embeddings` tự cung cấp `aembed_documents`/`aembed_query`
    (chạy qua executor mặc định), không cần tự viết bản async riêng."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = _get_model().encode(texts, normalize_embeddings=True)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = _get_model().encode([text], normalize_embeddings=True)[0]
        return vector.tolist()


_embeddings: LocalEmbeddings | None = None


def get_embeddings() -> LocalEmbeddings:
    """Instance dùng chung của process — luôn cùng model / số chiều (`EMBEDDING_DIM`) với lúc ingest."""
    global _embeddings
    if _embeddings is None:
        _embeddings = LocalEmbeddings()
    return _embeddings

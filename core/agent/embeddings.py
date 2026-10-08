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
    """Chỉ cài sync"""

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

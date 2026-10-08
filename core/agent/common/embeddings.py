import httpx
from langchain_core.embeddings import Embeddings

from app.config.settings import settings
from app.infra.text_clean import clean_text

EMBEDDING_MODEL_NAME = settings.EMBEDDING_MODEL
EMBEDDING_DIM = settings.EMBEDDING_DIM

_BATCH = 32
# Qwen3-Embedding được huấn luyện với query dạng "Instruct: ...\nQuery: ..." (đoạn văn thì để nguyên)
_QUERY_INSTRUCTION = "Given a Vietnamese or English dermatology question, retrieve relevant textbook passages that answer it"


def _embed(texts: list[str]) -> list[list[float]]:
    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError("Thiếu OPENROUTER_API_KEY để gọi embedding.")
    texts = [clean_text(t) for t in texts]
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        resp = httpx.post(
            f"{settings.OPENROUTER_BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
            json={"model": EMBEDDING_MODEL_NAME, "input": texts[i : i + _BATCH], "encoding_format": "float"},
            timeout=120,
        )
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        vectors += [d["embedding"] for d in data]
    if vectors and len(vectors[0]) != EMBEDDING_DIM:
        raise RuntimeError(f"{EMBEDDING_MODEL_NAME} trả {len(vectors[0])} chiều, khác EMBEDDING_DIM={EMBEDDING_DIM}.")
    return vectors


class OpenRouterEmbeddings(Embeddings):
    """Chỉ cài sync"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return _embed([f"Instruct: {_QUERY_INSTRUCTION}\nQuery: {text}"])[0]


_embeddings: OpenRouterEmbeddings | None = None


def get_embeddings() -> OpenRouterEmbeddings:
    """Instance dùng chung của process — luôn cùng model / số chiều (`EMBEDDING_DIM`) với lúc ingest."""
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenRouterEmbeddings()
    return _embeddings

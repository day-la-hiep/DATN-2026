"""Mã hoá văn bản thành sparse vector BM25 để Qdrant tự chấm điểm"""
import zlib
from collections import Counter

from qdrant_client.models import SparseVector

from app.infra.bm25.tokenizer import LANGUAGES, tokenize, tokenize_with_folds

SPARSE_NAME = "bm25"  # tên sparse vector trong collection chunk sách

_K1 = 1.2
_B = 0.75
# Độ dài trung bình giả định của một chunk (số từ). Không biết trước trung bình của cả kho khi nạp từng batch, nên cố định một
# hằng số như fastembed; sai lệch chỉ làm mức phạt độ dài hơi lệch, không đổi thứ tự quá nhiều.
_AVG_DOC_LEN = 256
# Token bỏ dấu để câu hỏi không dấu ("vay nen") vẫn khớp; trọng số thấp vì bỏ dấu gộp các từ khác nghĩa (ma / má / mạ)
_FOLD_WEIGHT = 0.3


def _token_id(token: str) -> int:
    # Qdrant chỉ nhận chỉ số uint32; crc32 ổn định giữa các tiến trình (hash() của Python thì không). Va chạm hiếm với
    # vài chục nghìn từ vựng và chỉ làm hai từ chia sẻ điểm, chấp nhận được.
    return zlib.crc32(token.encode("utf-8"))


def encode_document(text: str, language: str = "mixed") -> SparseVector:
    """Phần TF của BM25 cho một chunk: tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))."""
    tokens, folds = tokenize_with_folds(text, language)
    if not tokens:
        return SparseVector(indices=[], values=[])
    norm = _K1 * (1 - _B + _B * len(tokens) / _AVG_DOC_LEN)  # độ dài tính theo token chính, token bỏ dấu không làm đoạn "dài" hơn
    weights: dict[int, float] = {}
    for token, tf in Counter([*tokens, *folds]).items():
        # cộng dồn khi hai từ va chạm cùng chỉ số, vì Qdrant yêu cầu chỉ số không trùng
        idx = _token_id(token)
        weights[idx] = weights.get(idx, 0.0) + tf * (_K1 + 1) / (tf + norm)
    return SparseVector(indices=list(weights), values=list(weights.values()))


def encode_query(text: str, language: str = "mixed") -> SparseVector:
    """Từ chính trọng số 1, từ bỏ dấu `_FOLD_WEIGHT`; Qdrant nhân IDF của từ đó khi tính điểm."""
    tokens, folds = tokenize_with_folds(text, language, all_tokens=True)
    weights: dict[int, float] = {}
    for token, weight in [*((t, 1.0) for t in tokens), *((t, _FOLD_WEIGHT) for t in folds)]:
        idx = _token_id(token)
        weights[idx] = max(weights.get(idx, 0.0), weight)
    return SparseVector(indices=list(weights), values=list(weights.values()))

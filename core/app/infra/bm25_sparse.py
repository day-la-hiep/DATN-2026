"""Mã hoá văn bản thành sparse vector BM25 để Qdrant tự chấm điểm"""
import re
import unicodedata
import zlib
from collections import Counter

from qdrant_client.models import SparseVector

SPARSE_NAME = "bm25"  # tên sparse vector trong collection chunk sách

_K1 = 1.2
_B = 0.75
# Độ dài trung bình giả định của một chunk (số từ). Không biết trước trung bình của cả kho khi nạp từng batch, nên cố định một
# hằng số như fastembed; sai lệch chỉ làm mức phạt độ dài hơi lệch, không đổi thứ tự quá nhiều.
_AVG_DOC_LEN = 256

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Chữ thường, tách theo từ (âm tiết với tiếng Việt). Giữ dấu: bỏ dấu sẽ gộp các từ khác nghĩa ("ma" / "má" / "mạ")."""
    return _TOKEN_RE.findall(unicodedata.normalize("NFC", text).lower())


def _token_id(token: str) -> int:
    # Qdrant chỉ nhận chỉ số uint32; crc32 ổn định giữa các tiến trình (hash() của Python thì không). Va chạm hiếm với
    # vài chục nghìn từ vựng và chỉ làm hai từ chia sẻ điểm, chấp nhận được.
    return zlib.crc32(token.encode("utf-8"))


def encode_document(text: str) -> SparseVector:
    """Phần TF của BM25 cho một chunk: tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))."""
    tokens = tokenize(text)
    if not tokens:
        return SparseVector(indices=[], values=[])
    norm = _K1 * (1 - _B + _B * len(tokens) / _AVG_DOC_LEN)
    weights: dict[int, float] = {}
    for token, tf in Counter(tokens).items():
        # cộng dồn khi hai từ va chạm cùng chỉ số, vì Qdrant yêu cầu chỉ số không trùng
        idx = _token_id(token)
        weights[idx] = weights.get(idx, 0.0) + tf * (_K1 + 1) / (tf + norm)
    return SparseVector(indices=list(weights), values=list(weights.values()))


def encode_query(text: str) -> SparseVector:
    """Mỗi từ khác nhau của câu hỏi một trọng số 1; Qdrant nhân IDF của từ đó khi tính điểm."""
    indices = list(dict.fromkeys(_token_id(t) for t in tokenize(text)))
    return SparseVector(indices=indices, values=[1.0] * len(indices))

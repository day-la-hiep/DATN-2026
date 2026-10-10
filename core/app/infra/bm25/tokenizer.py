import re
import unicodedata
from functools import lru_cache

from nltk.stem import SnowballStemmer

from app.infra.bm25.stopwords import get_stopwords
from app.infra.text_clean import clean_text

LANGUAGES = ("vi", "en", "mixed")
_WORD_RE = re.compile(r"[^\W_]+(?:[-/][^\W_]+)*")  # "il-17", "5-fu" là một từ
_stemmer = SnowballStemmer("english")


@lru_cache(maxsize=200_000)
def _stem(token: str) -> str:
    return _stemmer.stem(token)


def _segments(text: str, language: str) -> list[str]:
    if language == "en":
        return text.split()
    from underthesea import word_tokenize  # nạp chậm: sách tiếng Anh không cần model tách từ

    tokens = word_tokenize(text)
    assert isinstance(tokens, list)  # format mặc định trả list
    return tokens


def _segment_tokens(segment: str) -> list[str]:
    seg = segment.lower()
    if " " in seg and not seg.isascii():
        # từ ghép tiếng Việt: giữ cả từ ghép lẫn âm tiết, vì ngữ cảnh khác nhau (câu hỏi ngắn / đoạn dài) có thể được tách khác nhau
        words: list[str] = _WORD_RE.findall(seg)
        if len(words) > 1:
            return ["_".join(words), *words]
        return words
    tokens: list[str] = []
    for word in _WORD_RE.findall(seg):
        tokens.append(word)
        if "-" in word or "/" in word:
            tokens += re.split(r"[-/]", word)  # "IL 17" vẫn khớp "il-17"
    return tokens


def _fold(token: str) -> str:
    return "~" + "".join(c for c in unicodedata.normalize("NFD", token) if not unicodedata.combining(c)).replace("đ", "d")


def tokenize_with_folds(text: str, language: str = "mixed", *, all_tokens: bool = False) -> tuple[list[str], list[str]]:
    """(token chính, token bỏ dấu `~...`). Bỏ dấu lấy từ token trước khi stem để hai phía luôn ra cùng chuỗi.

    Phía đoạn chỉ cần token bỏ dấu của từ có dấu; phía câu hỏi (`all_tokens`) thêm cho mọi từ, vì người dùng gõ không dấu thì
    token của họ đã là ASCII."""
    stopwords = get_stopwords(language)
    stem = language != "vi"
    tokens: list[str] = []
    folds: list[str] = []
    for segment in _segments(clean_text(text), language):
        for token in _segment_tokens(segment):
            if token in stopwords:
                continue
            tokens.append(_stem(token) if stem and token.isascii() and token.isalpha() else token)
            if all_tokens or not token.isascii():
                folds.append(_fold(token))
    return tokens, folds


def tokenize(text: str, language: str = "mixed") -> list[str]:
    """Làm sạch, tách từ, bỏ dấu câu, bỏ stopword, stem tiếng Anh. Token chính giữ dấu tiếng Việt: bỏ dấu sẽ gộp các từ khác nghĩa ("ma" / "má" / "mạ")."""
    return tokenize_with_folds(text, language)[0]

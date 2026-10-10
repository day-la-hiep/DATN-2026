import logging
from collections.abc import Callable
from functools import lru_cache

logger = logging.getLogger(__name__)

STOPWORD_SOURCE = "builtin"  # "nltk" = corpus nltk (chỉ có tiếng Anh); đổi là đổi tokenizer nên phải index lại sách

# Phủ định và đơn vị/liều mang nghĩa lâm sàng ("không có dị ứng", "5 mg"): không bao giờ bỏ, kể cả khi nguồn stopword có chứa
PROTECTED = frozenset({
    "không", "chưa", "chẳng", "chả", "no", "not", "nor", "without", "never",
    "mg", "mcg", "g", "kg", "ml", "l", "iu", "%",
})

_VI = frozenset(
    "và của là các những một được bị bởi cho với trong ngoài trên dưới tại từ đến khi nếu thì mà này đó kia ấy nên cũng đã đang sẽ "
    "vẫn còn rất hơn như về theo để do vì bằng hay hoặc nhưng song các mỗi mọi lại ra vào lên xuống".split()
)
_EN = frozenset(
    "a an the and or but if of at by for with about as into on in to from up down out over under is are was were be been being "
    "am do does did have has had this that these those it its which who whom whose what when where why how there here than then "
    "so such can could will would shall should may might also".split()
)


def _builtin(lang: str) -> frozenset[str]:
    return {"vi": _VI, "en": _EN}[lang]


def _nltk(lang: str) -> frozenset[str]:
    if lang != "en":
        return _builtin(lang)
    try:
        import nltk
        from nltk.corpus import stopwords

        try:
            return frozenset(stopwords.words("english"))
        except LookupError:
            nltk.download("stopwords", quiet=True)
            return frozenset(stopwords.words("english"))
    except Exception as exc:  # noqa: BLE001  # offline / không tải được corpus -> không làm hỏng việc index
        logger.warning("không dùng được stopword nltk (%s) — dùng danh sách có sẵn", exc)
        return _builtin(lang)


_SOURCES: dict[str, Callable[[str], frozenset[str]]] = {"builtin": _builtin, "nltk": _nltk}


@lru_cache
def get_stopwords(language: str) -> frozenset[str]:
    """Stopword cho `vi` / `en` / `mixed` (hợp của hai), đã trừ `PROTECTED`."""
    load = _SOURCES[STOPWORD_SOURCE]
    words = load("vi") | load("en") if language == "mixed" else load(language)
    return words - PROTECTED

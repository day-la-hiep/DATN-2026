import re
import unicodedata

_INVISIBLE = re.compile(r"[​-‏⁠﻿­]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_BREAK = re.compile(r"(\w)-[ \t]*\n[ \t]*(\w)")
_SPACES = re.compile(r"[ \t\r\f\v ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_PUNCT = str.maketrans({"–": "-", "—": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"'})
_GREEK = str.maketrans({"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "κ": "kappa", "μ": "mu", "ω": "omega"})


def _join_break(m: re.Match[str]) -> str:
    # chỉ nối khi sau gạch là chữ thường ("psori-\nasis"); "IL-\n17" hay "Anti-\nTNF" là gạch nối thật nên giữ
    return m.group(1) + m.group(2) if m.group(2).islower() else m.group(0)


def clean_text(text: str) -> str:
    """Làm sạch nhiễu OCR/PDF; dùng chung cho dense và BM25 nên không stemming/bỏ stopword ở đây."""
    text = unicodedata.normalize("NFC", text)
    text = _INVISIBLE.sub("", _CONTROL.sub("", text)).translate(_PUNCT).translate(_GREEK)
    text = _HYPHEN_BREAK.sub(_join_break, text)
    return _BLANK_LINES.sub("\n\n", _SPACES.sub(" ", text)).strip()

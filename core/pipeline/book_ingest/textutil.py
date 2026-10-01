"""Tiện ích văn bản chịu OCR nhiễu, dùng chung mọi bước."""
import hashlib
import re
import unicodedata


def norm(s: str) -> str:
    """Chữ thường, bỏ dấu, chỉ giữ a-z0-9 và khoảng trắng — để so khớp tên chịu nhiễu OCR."""
    s = unicodedata.normalize("NFKD", s.replace("đ", "d").replace("Đ", "D")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def slugify(s: str) -> str:
    return norm(s).replace(" ", "_") or "untitled"


def sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def upper_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    return sum(c.isupper() for c in letters) / len(letters)


def parse_page_ranges(specs: list[str], total: int) -> set[int]:
    """["1-30", "940"] -> {1..30, 940}, cắt theo [1, total]."""
    out: set[int] = set()
    for spec in specs:
        spec = spec.strip()
        if not spec:
            continue
        a, _, b = spec.partition("-")
        try:
            lo, hi = int(a), int(b or a)
        except ValueError:
            continue
        out.update(range(max(1, lo), min(total, hi) + 1))
    return out


def noise_score(text: str) -> float:
    """Tỉ lệ token 'lạ' (chữ hoa lẫn giữa từ, ký tự ~ ^ \\ { } chen giữa chữ...) — chỉ để xếp hạng
    trang nhiễu cho người duyệt, không phải thước đo tuyệt đối."""
    toks = re.findall(r"\S{4,}", text)
    if not toks:
        return 0.0
    bad = 0
    for t in toks:
        core = t.strip(".,;:()[]\"'")
        if re.search(r"[a-z][A-Z]", core) or re.search(r"[A-Za-z][~^\\{}|@#$%*_=<>][A-Za-z]", core):
            bad += 1
    return round(bad / len(toks), 4)

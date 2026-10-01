"""Cấu hình riêng từng sách: validate (từ dict JSON trong bảng `books.profile`) + tạo mặc định. Đọc/ghi ở `app/services/book_service.py`."""
from typing import Any

from pydantic import ValidationError

from app.models.book_profile import Profile


class ProfileError(ValueError):
    pass


def profile_from_dict(raw: dict[str, Any], book_id: str) -> Profile:
    if not isinstance(raw, dict):
        raise ProfileError("cài đặt phải là một object JSON")
    raw = dict(raw)
    raw.setdefault("book_id", book_id)
    if raw["book_id"] != book_id:
        raise ProfileError(f"book_id trong profile ({raw['book_id']!r}) khác sách hiện tại ({book_id!r})")
    try:
        return Profile.model_validate(raw)
    except ValidationError as e:
        raise ProfileError("; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())) from e


def default_profile(book_id: str, title: str, engine: str | None = None) -> Profile:
    prof = Profile(book_id=book_id, title=title or book_id)
    if engine:
        if engine not in {"pdftotext", "docling"}:
            raise ProfileError(f"engine không hợp lệ: {engine!r} (pdftotext | docling)")
        prof.extraction.engine = engine  # type: ignore[assignment]
    return prof

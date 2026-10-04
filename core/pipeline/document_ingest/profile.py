"""Cấu hình riêng từng tài liệu: tạo mặc định. Đọc/ghi (JSON trong `documents.profile`) ở `app/repositories/document_repository.py`."""
from app.models.document_profile import Profile


class ProfileError(ValueError):
    pass


def default_profile(document_id: str, engine: str | None = None) -> Profile:
    prof = Profile(document_id=document_id)
    if engine:
        if engine not in {"pdftotext", "docling"}:
            raise ProfileError(f"engine không hợp lệ: {engine!r} (pdftotext | docling)")
        prof.extraction.engine = engine  # type: ignore[assignment]
    return prof

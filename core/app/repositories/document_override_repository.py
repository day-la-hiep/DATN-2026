"""Override của người duyệt lên kết quả một bước"""

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exception.errors import NotFoundError
from app.models.document import Document, DocumentOverride, DocumentStage

SessionFactory = Callable[[], Session]


def _deep_merge(dst: dict[str, Any], patch: dict[str, Any]) -> None:
    """Gộp đệ quy `patch` vào `dst`; giá trị None xoá khoá (hoàn tác một override)."""
    for k, v in patch.items():
        if v is None:
            dst.pop(k, None)
        elif isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


class DocumentOverrideRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    @contextmanager
    def _tx(self):
        with self._sessions() as s, s.begin():
            yield s

    @staticmethod
    def _stage_row_id(s: Session, document_id: str, stage_id: str) -> str | None:
        """Override trỏ tới dòng bước (`document_stages.id`), nên cần tra id bước từ (tài liệu, mã bước) trước."""
        return s.scalars(
            select(DocumentStage.id).where(DocumentStage.document_id == document_id, DocumentStage.stage_id == stage_id)
        ).first()

    def get(self, document_id: str, stage_id: str) -> dict[str, Any]:
        with self._sessions() as s:
            stage_row_id = self._stage_row_id(s, document_id, stage_id)
            row = s.get(DocumentOverride, stage_row_id) if stage_row_id else None
            return dict(row.data) if row is not None else {}

    def _set(
        self,
        document_id: str,
        stage_id: str,
        change: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        with self._tx() as s:
            # khoá dòng tài liệu (không phải dòng override, có thể chưa tồn tại): hai lần sửa cùng lúc không ghi đè nhau
            if s.scalars(select(Document).where(Document.id == document_id).with_for_update()).first() is None:
                raise NotFoundError(document_id)
            stage_row_id = self._stage_row_id(s, document_id, stage_id)
            if stage_row_id is None:
                raise NotFoundError(f"{document_id}/{stage_id}")
            row = s.get(DocumentOverride, stage_row_id)
            data = change(dict(row.data) if row is not None else {})
            if row is None:
                s.add(DocumentOverride(document_stage_id=stage_row_id, data=data))
            else:
                row.data = data
            return data

    def update(self, document_id: str, stage_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Gộp `patch` vào override của bước. Giá trị None xoá khoá."""

        def merge(cur: dict[str, Any]) -> dict[str, Any]:
            _deep_merge(cur, patch)
            return cur

        return self._set(document_id, stage_id, merge)

    def write(self, document_id: str, stage_id: str, data: dict[str, Any]) -> None:
        """Ghi đè toàn bộ override (không merge) — dùng khi caller đã tự gộp xong."""
        self._set(document_id, stage_id, lambda _: data)

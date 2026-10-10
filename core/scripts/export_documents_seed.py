"""Xuất record tài liệu RAG hiện có (documents + stages + overrides + files) ra `scripts/seed_documents.json` để `init_db.py` khôi phục."""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.api.deps import get_postgres_client  # noqa: E402
from app.models.document import Document, DocumentOverride, DocumentStage  # noqa: E402
from app.models.file import File  # noqa: E402

OUT = Path(__file__).with_name("seed_documents.json")


def _row(obj: object) -> dict:
    out = {}
    for col in obj.__table__.columns:  # type: ignore[attr-defined]
        v = getattr(obj, col.key)
        out[col.key] = v.isoformat() if isinstance(v, datetime) else v
    return out


def main() -> None:
    with get_postgres_client().sync_session_factory() as s:
        docs = list(s.scalars(select(Document).order_by(Document.created_at)))
        file_ids = {i for d in docs for i in (d.source_file_id, d.ingested_file_id) if i}
        stages = list(s.scalars(select(DocumentStage).where(DocumentStage.document_id.in_([d.id for d in docs]))))
        overrides = list(
            s.scalars(select(DocumentOverride).where(DocumentOverride.document_stage_id.in_([st.id for st in stages])))
        )
        files = list(s.scalars(select(File).where(File.id.in_(file_ids))))
        data = {
            "files": [_row(f) for f in files],
            "documents": [_row(d) for d in docs],
            "document_stages": [_row(st) for st in stages],
            "document_overrides": [_row(o) for o in overrides],
        }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã xuất {len(docs)} tài liệu, {len(stages)} bước, {len(overrides)} override, {len(files)} file -> {OUT.name}")


if __name__ == "__main__":
    main()

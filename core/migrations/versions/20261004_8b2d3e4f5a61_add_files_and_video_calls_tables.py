"""add files and video calls tables

Revision ID: 8b2d3e4f5a61
Revises: 7a1c2d3e4f50
Create Date: 2026-10-04 23:00:00

Bảng `files` theo `app/dto/base/file.py::File` (xem `docs/plan-db-mapping.md` mục 5.7):
- `documents.source_file_id` / `ingested_file_id` thay cho `pdf_name` / `pdf_bytes` (dữ liệu cũ chuyển sang dòng `files`).
- `message_files` nối tin nhắn với tệp đính kèm thay cho bản sao `attached_files` trong `messages.metadata`.
- `video_calls` theo `app/dto/base/video_call.py::VideoCall` (có vòng đời riêng nên tách khỏi `messages.metadata`);
  tin `message_type="video_call"` trỏ tới qua `messages.video_call_id`. Hiện chưa có dữ liệu cuộc gọi nào để chuyển.
- `documents.id` do DB sinh như các bảng khác.

Viết tay vì có bước chuyển dữ liệu (autogenerate chỉ sinh drop cột).
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8b2d3e4f5a61"
down_revision: Union[str, Sequence[str], None] = "7a1c2d3e4f50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = sa.text("gen_random_uuid()")


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "files",
        sa.Column("id", sa.String(64), server_default=_UUID, nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_files_storage_key")),
    )

    # ---- documents: pdf_name/pdf_bytes -> dòng files ----------------------------------------------------------------
    op.alter_column("documents", "id", server_default=_UUID)
    op.add_column("documents", sa.Column("source_file_id", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("ingested_file_id", sa.String(64), nullable=True))
    op.create_foreign_key(op.f("fk_documents_source_file_id_files"), "documents", "files",
                          ["source_file_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(op.f("fk_documents_ingested_file_id_files"), "documents", "files",
                          ["ingested_file_id"], ["id"], ondelete="SET NULL")
    bind.execute(sa.text(
        "INSERT INTO files (file_name, storage_key, content_type, size, created_at) "
        "SELECT COALESCE(NULLIF(pdf_name, ''), 'source.pdf'), 'document/' || id || '/source.pdf', 'application/pdf', "
        "pdf_bytes, created_at FROM documents WHERE pdf_bytes IS NOT NULL OR pdf_name <> ''"
    ))
    bind.execute(sa.text(
        "UPDATE documents d SET source_file_id = f.id FROM files f WHERE f.storage_key = 'document/' || d.id || '/source.pdf'"
    ))
    # `pages.jsonl` có khi bước ingest đã chạy xong (trạng thái lưu trong DB; kích thước chưa biết — ghi khi chạy lại bước)
    bind.execute(sa.text(
        "INSERT INTO files (file_name, storage_key, content_type, size, created_at) "
        "SELECT 'pages.jsonl', 'document/' || s.document_id || '/pages.jsonl', 'application/x-ndjson', NULL, "
        "COALESCE(s.finished_at, now()) FROM document_stages s "
        "WHERE s.stage_id = 'ingest' AND s.state IN ('pending_review', 'approved', 'stale')"
    ))
    bind.execute(sa.text(
        "UPDATE documents d SET ingested_file_id = f.id FROM files f WHERE f.storage_key = 'document/' || d.id || '/pages.jsonl'"
    ))
    op.drop_column("documents", "pdf_name")
    op.drop_column("documents", "pdf_bytes")

    # ---- message_files: attached_files trong metadata -> dòng files + liên kết ---------------------------------------
    op.create_table(
        "message_files",
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("file_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], name=op.f("fk_message_files_message_id_messages"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], name=op.f("fk_message_files_file_id_files"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id", "file_id", name=op.f("pk_message_files")),
    )
    op.create_table(
        "video_calls",
        sa.Column("id", sa.String(64), server_default=_UUID, nullable=False),
        sa.Column("room_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_calls")),
        sa.UniqueConstraint("room_id", name=op.f("uq_video_calls_room_id")),
    )
    op.add_column("messages", sa.Column("video_call_id", sa.String(64), nullable=True))
    op.create_foreign_key(op.f("fk_messages_video_call_id_video_calls"), "messages", "video_calls",
                          ["video_call_id"], ["id"], ondelete="SET NULL")

    rows = bind.execute(sa.text("SELECT id, metadata, created_at FROM messages WHERE metadata ? 'attached_files'")).all()
    for mid, meta, created_at in rows:
        for f in meta.pop("attached_files") or []:
            fid = bind.execute(
                sa.text("INSERT INTO files (file_name, storage_key, content_type, size, created_at) "
                        "VALUES (:n, :k, :t, :s, :c) ON CONFLICT (storage_key) DO UPDATE SET file_name = EXCLUDED.file_name "
                        "RETURNING id"),
                {"n": f.get("file_name", ""), "k": f["storage_key"], "t": f.get("content_type"), "s": f.get("size"),
                 "c": created_at},
            ).scalar_one()
            bind.execute(sa.text("INSERT INTO message_files (message_id, file_id) VALUES (:m, :f) ON CONFLICT DO NOTHING"),
                         {"m": mid, "f": fid})
        bind.execute(sa.text("UPDATE messages SET metadata = CAST(:m AS JSONB) WHERE id = :id"),
                     {"m": json.dumps(meta, ensure_ascii=False), "id": mid})


def downgrade() -> None:
    bind = op.get_bind()
    # đính kèm: chép File trở lại `metadata.attached_files`
    for mid, f in bind.execute(sa.text(
        "SELECT mf.message_id, json_build_object('file_name', f.file_name, 'storage_key', f.storage_key, "
        "'content_type', f.content_type, 'size', f.size) FROM message_files mf JOIN files f ON f.id = mf.file_id"
    )).all():
        bind.execute(sa.text(
            # metadata có thể là SQL NULL hoặc JSON `null` -> coi như object rỗng
            "UPDATE messages SET metadata = jsonb_set(CASE WHEN jsonb_typeof(metadata) = 'object' THEN metadata "
            "ELSE '{}'::jsonb END, '{attached_files}', "
            "COALESCE(metadata->'attached_files', '[]'::jsonb) || CAST(:f AS JSONB)) WHERE id = :m"
        ), {"f": json.dumps([f]), "m": mid})
    op.drop_table("message_files")
    op.drop_constraint(op.f("fk_messages_video_call_id_video_calls"), "messages", type_="foreignkey")
    op.drop_column("messages", "video_call_id")
    op.drop_table("video_calls")

    op.add_column("documents", sa.Column("pdf_name", sa.String(255), nullable=True))
    op.add_column("documents", sa.Column("pdf_bytes", sa.Integer(), nullable=True))
    bind.execute(sa.text(
        "UPDATE documents d SET pdf_name = f.file_name, pdf_bytes = f.size FROM files f WHERE f.id = d.source_file_id"
    ))
    bind.execute(sa.text("UPDATE documents SET pdf_name = '' WHERE pdf_name IS NULL"))
    op.alter_column("documents", "pdf_name", nullable=False)
    op.drop_constraint(op.f("fk_documents_ingested_file_id_files"), "documents", type_="foreignkey")
    op.drop_constraint(op.f("fk_documents_source_file_id_files"), "documents", type_="foreignkey")
    op.drop_column("documents", "ingested_file_id")
    op.drop_column("documents", "source_file_id")
    op.alter_column("documents", "id", server_default=None)
    op.drop_table("files")

"""align schema with base entities

Revision ID: 7a1c2d3e4f50
Revises: 6e7b779ba7c1
Create Date: 2026-10-04 21:30:00

Đưa schema về khớp `app/dto/base/` (xem `docs/plan-db-mapping.md`):
- PK của `users`, `conversations`, `messages`, `patient_profiles`, `consultation_sessions` do DB sinh (`gen_random_uuid()`).
- `users` theo `User`; tách `doctors`/`admins` (PK = FK tới `users.id`); thêm `patient_profiles`, `consultation_sessions`.
- `conversations.patient_profile_id` thay `user_id` (chủ hội thoại suy ra qua hồ sơ); `messages.role` -> `sender`, thêm `message_type`, `consultation_session_id`; `documents.type`.
- Chuyển dữ liệu đã lưu theo quy ước cũ sang quy ước hiện tại (metadata tin nhắn, summary của bước) để code chạy không cần
  nhánh tương thích.

Viết tay: autogenerate không nhận ra đổi tên cột (`name`->`full_name`, `role`->`sender`) và sẽ sinh drop + add (mất dữ liệu).
Dữ liệu user không cần giữ (chưa có đăng nhập/đăng ký): `user-1` được ghi lại theo init data; hội thoại/tin nhắn/tài liệu giữ nguyên.
"""
import json
import re
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7a1c2d3e4f50"
down_revision: Union[str, Sequence[str], None] = "6e7b779ba7c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Init data của user mặc định — PHẢI khớp `scripts/init_db.py::USERS` (lặp lại ở đây vì migration không import code app).
USER_1 = {"username": "user-1", "full_name": "Nguyễn Văn An", "dob": "1995-05-20", "gender": "male"}

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


def _snake(d: Any, deep: bool) -> Any:
    if isinstance(d, dict):
        return {(_CAMEL.sub("_", k).lower() if isinstance(k, str) else k): (_snake(v, True) if deep else v) for k, v in d.items()}
    if deep and isinstance(d, list):
        return [_snake(v, True) for v in d]
    return d


def _upgrade_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """`choice` từng lưu camelCase (`questionId`...); `attachments: [{id, name, size, type, url}]` nay là `attached_files`."""
    out = dict(meta)
    if isinstance(out.get("choice"), dict):
        out["choice"] = _snake(out["choice"], True)
    for step in out.get("reasoning") or []:
        if isinstance(step, dict) and isinstance(step.get("choice"), dict):
            step["choice"] = _snake(step["choice"], True)
    if "attachments" in out:
        out["attached_files"] = [
            {"file_name": a.get("name", ""), "storage_key": a.get("id", ""), "content_type": a.get("type"),
             "size": a.get("size"), "url": a.get("url")}
            for a in out.pop("attachments") or []
        ]
    out.pop("selection_ref", None)  # tính năng trích dẫn tin nhắn đã bỏ
    return out


_UUID = sa.text("gen_random_uuid()::text")  # PK do DB sinh; id cũ (`conv-…`, `msg-…`, `user-1`) vẫn là chuỗi hợp lệ
_PK_TABLES = ("users", "conversations", "messages")


def upgrade() -> None:
    bind = op.get_bind()
    for table in _PK_TABLES:
        op.alter_column(table, "id", server_default=_UUID)

    # ---- users ← User -------------------------------------------------------------------------------------------
    op.alter_column("users", "name", new_column_name="full_name")
    op.drop_column("users", "email")
    op.add_column("users", sa.Column("username", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("dob", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(16), nullable=True))
    # dữ liệu user không cần giữ: user-1 theo init data, user khác (nếu có) nhận giá trị tạm để đặt NOT NULL
    bind.execute(sa.text(
        "UPDATE users SET username = id, full_name = COALESCE(full_name, id), dob = DATE '1970-01-01', gender = 'male'"
    ))
    bind.execute(
        sa.text("UPDATE users SET username = :username, full_name = :full_name, dob = CAST(:dob AS DATE), gender = :gender "
                "WHERE id = 'user-1'"),
        USER_1,
    )
    for col in ("username", "full_name", "dob", "gender"):
        op.alter_column("users", col, nullable=False)
    op.create_unique_constraint(op.f("uq_users_username"), "users", ["username"])

    # ---- doctors, admins ← Doctor, Admin (PK = FK tới users.id) --------------------------------------------------
    op.create_table(
        "doctors",
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_doctors_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_doctors")),
    )
    op.create_table(
        "admins",
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_admins_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_admins")),
    )

    # ---- patient_profiles ← PatientProfile -----------------------------------------------------------------------
    op.create_table(
        "patient_profiles",
        sa.Column("id", sa.String(64), server_default=_UUID, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("dob", sa.Date(), nullable=False),
        sa.Column("gender", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_patient_profiles_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_profiles")),
    )
    op.create_index(op.f("ix_patient_profiles_user_id"), "patient_profiles", ["user_id"])
    # hồ sơ mặc định "chính mình" cho mỗi user — cùng quy ước id với `scripts/init_db.py`
    bind.execute(sa.text(
        "INSERT INTO patient_profiles (id, user_id, full_name, dob, gender, created_at) "
        "SELECT 'pp-' || id || '-self', id, full_name, dob, gender, now() FROM users"
    ))

    # ---- conversations.patient_profile_id ← Conversation.patient -------------------------------------------------
    op.add_column("conversations", sa.Column("patient_profile_id", sa.String(64), nullable=True))
    bind.execute(sa.text("UPDATE conversations SET patient_profile_id = 'pp-' || user_id || '-self'"))
    op.alter_column("conversations", "patient_profile_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_conversations_patient_profile_id_patient_profiles"),
        "conversations", "patient_profiles", ["patient_profile_id"], ["id"],
    )
    # chủ hội thoại suy ra từ `patient_profiles.user_id` -> bỏ cột lặp
    op.drop_constraint(op.f("fk_conversations_user_id_users"), "conversations", type_="foreignkey")
    op.drop_column("conversations", "user_id")

    # ---- consultation_sessions ← ConsultationSession -------------------------------------------------------------
    op.create_table(
        "consultation_sessions",
        sa.Column("id", sa.String(64), server_default=_UUID, nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("doctor_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status = 'pending' OR doctor_id IS NOT NULL", name=op.f("ck_consultation_sessions_doctor_when_not_pending")),
        sa.CheckConstraint("status <> 'resolved' OR resolved_at IS NOT NULL", name=op.f("ck_consultation_sessions_resolved_at_when_resolved")),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"],
                                name=op.f("fk_consultation_sessions_conversation_id_conversations"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.user_id"],
                                name=op.f("fk_consultation_sessions_doctor_id_doctors"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consultation_sessions")),
    )
    op.create_index(op.f("ix_consultation_sessions_conversation_id"), "consultation_sessions", ["conversation_id"])
    op.create_index(
        "uq_consultation_sessions_open_per_conversation", "consultation_sessions", ["conversation_id"],
        unique=True, postgresql_where=sa.text("status <> 'resolved'"),
    )

    # ---- messages ← Message + MessageMetadata --------------------------------------------------------------------
    op.alter_column("messages", "role", new_column_name="sender")
    bind.execute(sa.text("UPDATE messages SET sender = CASE sender WHEN 'user' THEN 'patient' WHEN 'assistant' THEN 'ai' ELSE sender END"))
    op.add_column("messages", sa.Column("message_type", sa.String(32), server_default="text", nullable=False))
    op.add_column("messages", sa.Column("consultation_session_id", sa.String(64), nullable=True))
    op.create_foreign_key(
        op.f("fk_messages_consultation_session_id_consultation_sessions"),
        "messages", "consultation_sessions", ["consultation_session_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(op.f("ix_messages_consultation_session_id"), "messages", ["consultation_session_id"])
    rows = bind.execute(sa.text("SELECT id, metadata FROM messages WHERE metadata IS NOT NULL")).all()
    for mid, meta in rows:
        if not isinstance(meta, dict):  # metadata lưu JSON `null` (khác SQL NULL)
            continue
        new = _upgrade_metadata(meta)
        mtype = "attached" if new.get("attached_files") else "text"
        bind.execute(
            sa.text("UPDATE messages SET metadata = CAST(:m AS JSONB), message_type = :t WHERE id = :id"),
            {"m": json.dumps(new, ensure_ascii=False), "t": mtype, "id": mid},
        )

    # ---- documents.type ← Document.type; summary của bước: camelCase -> snake_case ---------------------------------
    op.add_column("documents", sa.Column("type", sa.String(16), server_default="book", nullable=False))
    for did, sid, summary in bind.execute(
        sa.text("SELECT document_id, stage_id, summary FROM document_stages WHERE summary IS NOT NULL")
    ).all():
        bind.execute(
            sa.text("UPDATE document_stages SET summary = CAST(:s AS JSONB) WHERE document_id = :d AND stage_id = :st"),
            {"s": json.dumps(_snake(summary, False), ensure_ascii=False), "d": did, "st": sid},
        )


def downgrade() -> None:
    # Dữ liệu chuyển đổi (metadata, summary) không đảo ngược — code cũ vẫn đọc được bản snake_case qua nhánh tương thích của nó.
    op.drop_column("documents", "type")

    op.drop_index(op.f("ix_messages_consultation_session_id"), table_name="messages")
    op.drop_constraint(op.f("fk_messages_consultation_session_id_consultation_sessions"), "messages", type_="foreignkey")
    op.drop_column("messages", "consultation_session_id")
    op.drop_column("messages", "message_type")
    op.execute("DELETE FROM messages WHERE sender = 'doctor'")  # bản cũ không có vai trò bác sĩ
    op.execute("UPDATE messages SET sender = CASE sender WHEN 'patient' THEN 'user' WHEN 'ai' THEN 'assistant' ELSE sender END")
    op.alter_column("messages", "sender", new_column_name="role")

    op.drop_index("uq_consultation_sessions_open_per_conversation", table_name="consultation_sessions")
    op.drop_index(op.f("ix_consultation_sessions_conversation_id"), table_name="consultation_sessions")
    op.drop_table("consultation_sessions")

    op.add_column("conversations", sa.Column("user_id", sa.String(64), nullable=True))
    op.execute("UPDATE conversations c SET user_id = p.user_id FROM patient_profiles p WHERE p.id = c.patient_profile_id")
    op.alter_column("conversations", "user_id", nullable=False)
    op.create_foreign_key(op.f("fk_conversations_user_id_users"), "conversations", "users", ["user_id"], ["id"])
    op.drop_constraint(op.f("fk_conversations_patient_profile_id_patient_profiles"), "conversations", type_="foreignkey")
    op.drop_column("conversations", "patient_profile_id")

    op.drop_index(op.f("ix_patient_profiles_user_id"), table_name="patient_profiles")
    op.drop_table("patient_profiles")
    op.drop_table("admins")
    op.drop_table("doctors")

    op.drop_constraint(op.f("uq_users_username"), "users", type_="unique")
    for col in ("gender", "dob", "username"):
        op.drop_column("users", col)
    op.add_column("users", sa.Column("email", sa.String(255), nullable=True))
    op.alter_column("users", "full_name", new_column_name="name", nullable=True)
    for table in _PK_TABLES:
        op.alter_column(table, "id", server_default=None)

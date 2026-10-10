"""Khởi tạo dữ liệu cho môi trường mới"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # chạy được từ `core/` mà không cần cài package

from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.deps import get_document_file_store, get_file_store_service, get_postgres_client  # noqa: E402
from app.config.security import hash_password  # noqa: E402
from app.models.admin import Admin  # noqa: E402
from app.models.doctor import Doctor  # noqa: E402
from app.models.document import Document, DocumentOverride, DocumentStage  # noqa: E402
from app.models.file import File  # noqa: E402
from app.models.patient_profile import PatientProfile  # noqa: E402
from app.models.user import User  # noqa: E402

# id cố định: FE hard-code `user-1`; hồ sơ `pp-<user_id>-self` cùng quy ước với migration `align_schema_with_base`.
# Giá trị của `user-1` PHẢI khớp `USER_1` trong migration đó.
DEFAULT_PASSWORD_HASH = hash_password("123456")

USERS = [
    {"id": "user-1", "username": "user-1", "full_name": "Nguyễn Văn An", "dob": date(1995, 5, 20), "gender": "male", "password_hash": DEFAULT_PASSWORD_HASH},
    {"id": "doctor-1", "username": "doctor-1", "full_name": "BS. Trần Thị Bình", "dob": date(1982, 3, 14), "gender": "female", "password_hash": DEFAULT_PASSWORD_HASH},
    {"id": "admin-1", "username": "admin-1", "full_name": "Quản trị viên", "dob": date(1990, 1, 1), "gender": "male", "password_hash": DEFAULT_PASSWORD_HASH},
]
DOCTORS = [{"user_id": "doctor-1", "description": "Bác sĩ chuyên khoa Da liễu (dữ liệu mẫu)."}]
ADMINS = [{"user_id": "admin-1"}]
DOCUMENTS_SEED = Path(__file__).with_name("seed_documents.json")  # sinh bằng `export_documents_seed.py`
PROFILE_OWNERS = ["user-1"]  # tài khoản bệnh nhân cần hồ sơ "chính mình" để tạo hội thoại


def _restore_documents(s: Session) -> list[str]:
    """Khôi phục record tài liệu RAG đã có; chỉ DB — file MinIO và point Qdrant nằm ngoài Postgres nên không bị reset theo."""
    if not DOCUMENTS_SEED.exists():
        return []
    data = json.loads(DOCUMENTS_SEED.read_text(encoding="utf-8"))

    def _dt(row: dict) -> dict:
        return {k: datetime.fromisoformat(v) if k.endswith("_at") and isinstance(v, str) else v for k, v in row.items()}

    created: list[str] = []
    for d in data["documents"]:
        if s.get(Document, d["id"]) is not None:
            continue
        for f in data["files"]:
            if f["id"] in (d["source_file_id"], d["ingested_file_id"]) and s.get(File, f["id"]) is None:
                s.add(File(**_dt(f)))
        s.flush()  # files phải có trước khi documents trỏ FK tới
        row = _dt(d)
        if row["uploaded_by_id"] and s.get(Doctor, row["uploaded_by_id"]) is None:
            row["uploaded_by_id"] = None
        s.add(Document(**row))
        s.flush()
        stage_ids = set()
        for st in data["document_stages"]:
            if st["document_id"] == d["id"]:
                s.add(DocumentStage(**_dt(st)))
                stage_ids.add(st["id"])
        s.flush()
        for o in data["document_overrides"]:
            if o["document_stage_id"] in stage_ids:
                s.add(DocumentOverride(**_dt(o)))
        created.append(f"document {d['id']}")
    s.commit()
    return created


def _check_migrated() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with get_postgres_client().sync_session_factory() as s:
        current = MigrationContext.configure(s.connection()).get_current_revision()
    if current != head:
        sys.exit(f"Database đang ở revision {current}, cần {head}. Chạy trước: cd core && uv run alembic upgrade head")


def _seed(s: Session) -> list[str]:
    created: list[str] = []
    for u in USERS:
        user_row = s.get(User, u["id"])
        if user_row is None:
            s.add(User(**u))
            created.append(f"user {u['id']}")
        elif user_row.password_hash is None and "password_hash" in u:
            user_row.password_hash = u["password_hash"]
            created.append(f"password for {u['id']}")
    s.flush()  # bảng con trỏ FK tới users
    for d in DOCTORS:
        if s.get(Doctor, d["user_id"]) is None:
            s.add(Doctor(**d))
            created.append(f"doctor {d['user_id']}")
    for a in ADMINS:
        if s.get(Admin, a["user_id"]) is None:
            s.add(Admin(**a))
            created.append(f"admin {a['user_id']}")
    for owner in PROFILE_OWNERS:
        pid = f"pp-{owner}-self"
        if s.get(PatientProfile, pid) is None:
            u = next(x for x in USERS if x["id"] == owner)
            s.add(PatientProfile(id=pid, user_id=owner, full_name=u["full_name"], dob=u["dob"], gender=u["gender"]))
            created.append(f"patient_profile {pid}")
    s.commit()
    return created


def main() -> None:
    _check_migrated()
    for store in (get_file_store_service(), get_document_file_store()):
        store.ensure_bucket()
    with get_postgres_client().sync_session_factory() as s:
        created = _seed(s) + _restore_documents(s)
    print("Đã tạo: " + ", ".join(created) if created else "Dữ liệu mẫu đã có sẵn, không tạo thêm.")


if __name__ == "__main__":
    main()

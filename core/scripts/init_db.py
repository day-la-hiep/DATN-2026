"""Khởi tạo dữ liệu cho môi trường mới"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # chạy được từ `core/` mà không cần cài package

from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.deps import get_document_file_store, get_file_store_service, get_postgres_client  # noqa: E402
from app.models.admin import Admin  # noqa: E402
from app.models.doctor import Doctor  # noqa: E402
from app.models.patient_profile import PatientProfile  # noqa: E402
from app.models.user import User  # noqa: E402

# id cố định: FE hard-code `user-1`; hồ sơ `pp-<user_id>-self` cùng quy ước với migration `align_schema_with_base`.
# Giá trị của `user-1` PHẢI khớp `USER_1` trong migration đó.
USERS = [
    {"id": "user-1", "username": "user-1", "full_name": "Nguyễn Văn An", "dob": date(1995, 5, 20), "gender": "male"},
    {"id": "doctor-1", "username": "doctor-1", "full_name": "BS. Trần Thị Bình", "dob": date(1982, 3, 14), "gender": "female"},
    {"id": "admin-1", "username": "admin-1", "full_name": "Quản trị viên", "dob": date(1990, 1, 1), "gender": "male"},
]
DOCTORS = [{"user_id": "doctor-1", "description": "Bác sĩ chuyên khoa Da liễu (dữ liệu mẫu)."}]
ADMINS = [{"user_id": "admin-1"}]
PROFILE_OWNERS = ["user-1"]  # tài khoản bệnh nhân cần hồ sơ "chính mình" để tạo hội thoại


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
        if s.get(User, u["id"]) is None:
            s.add(User(**u))
            created.append(f"user {u['id']}")
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
        created = _seed(s)
    print("Đã tạo: " + ", ".join(created) if created else "Dữ liệu mẫu đã có sẵn, không tạo thêm.")


if __name__ == "__main__":
    main()

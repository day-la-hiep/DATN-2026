"""
Script migrate bảng users từ schema cũ (id, name, email, created_at)
sang schema mới (id, username, full_name, dob, gender, password_hash, created_at)
rồi seed dữ liệu mẫu.

Chỉ chạy một lần khi DB còn schema cũ.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from app.config.security import hash_password  # noqa: E402

CONN_STR = "postgresql://postgres:postgres@localhost:5432/derma_hospital_db"
DEFAULT_PASSWORD_HASH = hash_password("123456")


def migrate_users_table(cur: psycopg.Cursor) -> None:
    """Đổi schema bảng users từ cũ sang mới (idempotent)."""
    # Kiểm tra nếu cột mới đã có thì bỏ qua
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='users' AND column_name='username'
    """)
    if cur.fetchone():
        print("[migrate] Schema users đã là phiên bản mới, bỏ qua migrate.")
        return

    print("[migrate] Đang migrate bảng users sang schema mới...")

    # 1. Đổi tên cột name -> full_name
    cur.execute("ALTER TABLE users RENAME COLUMN name TO full_name")

    # 2. Thêm các cột mới (nullable trước, điền giá trị mặc định, rồi đặt NOT NULL)
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(64)")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dob DATE")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(16)")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
    cur.execute("ALTER TABLE users DROP COLUMN IF EXISTS email")

    # 3. Điền giá trị tạm cho các dòng cũ
    cur.execute("""
        UPDATE users
        SET username = id,
            dob = '1990-01-01',
            gender = 'male'
        WHERE username IS NULL
    """)

    # 4. Đặt NOT NULL cho các cột bắt buộc
    cur.execute("ALTER TABLE users ALTER COLUMN username SET NOT NULL")
    cur.execute("ALTER TABLE users ADD CONSTRAINT users_username_unique UNIQUE (username)")
    cur.execute("ALTER TABLE users ALTER COLUMN full_name SET NOT NULL")
    cur.execute("ALTER TABLE users ALTER COLUMN dob SET NOT NULL")
    cur.execute("ALTER TABLE users ALTER COLUMN gender SET NOT NULL")

    print("[migrate] Bảng users đã được migrate thành công.")


USERS = [
    {"id": "user-1",    "username": "user-1",    "full_name": "Nguyen Van An",    "dob": "1995-05-20", "gender": "male"},
    {"id": "doctor-1",  "username": "doctor-1",  "full_name": "BS. Tran Thi Binh","dob": "1982-03-14", "gender": "female"},
    {"id": "admin-1",   "username": "admin-1",   "full_name": "Quan tri vien",     "dob": "1990-01-01", "gender": "male"},
]

DOCTORS = [{"user_id": "doctor-1", "description": "Bac si chuyen khoa Da lieu (du lieu mau)."}]
ADMINS  = [{"user_id": "admin-1"}]
PROFILES = [
    {"id": "pp-user-1-self",   "user_id": "user-1",   "full_name": "Nguyen Van An",    "dob": "1995-05-20", "gender": "male"},
]


def ensure_table(cur: psycopg.Cursor, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (table,))
    return cur.fetchone()[0] is not None  # type: ignore[index]


def seed(cur: psycopg.Cursor) -> list[str]:
    created: list[str] = []

    # -- users --
    for u in USERS:
        cur.execute("SELECT id FROM users WHERE id = %s", (u["id"],))
        if cur.fetchone():
            # Đặt mật khẩu nếu chưa có
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s AND password_hash IS NULL", (DEFAULT_PASSWORD_HASH, u["id"]))
            continue
        cur.execute("""
            INSERT INTO users (id, username, full_name, dob, gender, password_hash, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (u["id"], u["username"], u["full_name"], u["dob"], u["gender"], DEFAULT_PASSWORD_HASH))
        created.append(f"user {u['id']}")

    # -- doctors (nếu bảng tồn tại) --
    if ensure_table(cur, "doctors"):
        for d in DOCTORS:
            cur.execute("SELECT user_id FROM doctors WHERE user_id = %s", (d["user_id"],))
            if not cur.fetchone():
                cur.execute("INSERT INTO doctors (user_id, description) VALUES (%s, %s)", (d["user_id"], d["description"]))
                created.append(f"doctor {d['user_id']}")

    # -- admins --
    if ensure_table(cur, "admins"):
        for a in ADMINS:
            cur.execute("SELECT user_id FROM admins WHERE user_id = %s", (a["user_id"],))
            if not cur.fetchone():
                cur.execute("INSERT INTO admins (user_id) VALUES (%s)", (a["user_id"],))
                created.append(f"admin {a['user_id']}")

    # -- patient_profiles --
    if ensure_table(cur, "patient_profiles"):
        for p in PROFILES:
            cur.execute("SELECT id FROM patient_profiles WHERE id = %s", (p["id"],))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO patient_profiles (id, user_id, full_name, dob, gender, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (p["id"], p["user_id"], p["full_name"], p["dob"], p["gender"]))
                created.append(f"patient_profile {p['id']}")

    return created


def main() -> None:
    conn = psycopg.connect(CONN_STR)
    try:
        with conn.transaction():
            cur = conn.cursor()
            migrate_users_table(cur)
            created = seed(cur)
        if created:
            print("Da tao:", ", ".join(created))
        else:
            print("Du lieu mau da co san, khong tao them.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

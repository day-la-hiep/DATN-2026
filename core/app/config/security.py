"""Hàm tiện ích bảo mật: băm/kiểm tra mật khẩu bằng bcrypt và sinh/giải mã JWT token."""

from datetime import UTC, datetime, timedelta
import uuid

import bcrypt
import jwt

from app.config.settings import settings


def hash_password(password: str) -> str:
    """Băm mật khẩu sử dụng bcrypt salt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Kiểm tra mật khẩu thường so với hash lưu trong database."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    user_id: str,
    role: str,
    username: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Tạo Access Token JWT có thời hạn ngắn (mặc định 30 phút)."""
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(
    user_id: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, int]:
    """Tạo Refresh Token JWT có thời hạn dài (mặc định 30 ngày).

    Trả về: (token_str, jti_id, expire_timestamp_epoch)
    `jti` dùng để lưu và thu hồi token trong Redis.
    """
    now = datetime.now(UTC)
    expire = now + (
        expires_delta or timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    )
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "jti": jti,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token_str = jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return token_str, jti, int(expire.timestamp())


def decode_token(token: str) -> dict:
    """Giải mã và kiểm tra tính hợp lệ của token."""
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )

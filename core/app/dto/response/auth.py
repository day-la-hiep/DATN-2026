"""DTO Output cho luồng xác thực (Thông tin người dùng, cặp Token)."""

from datetime import date
from pydantic import BaseModel

from app.common.constant import Gender


class UserSummaryOutput(BaseModel):
    """Thông tin tóm tắt của tài khoản người dùng sau khi xác thực."""

    id: str
    username: str
    full_name: str
    dob: date
    gender: Gender
    role: str  # "patient" | "doctor" | "admin"


class TokenPairOutput(BaseModel):
    """Cặp Access Token và Refresh Token trả về cho client."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserSummaryOutput

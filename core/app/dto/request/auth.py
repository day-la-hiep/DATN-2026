"""DTO Input cho luồng xác thực (Đăng ký, Đăng nhập, Làm mới token)."""

from datetime import date
from pydantic import BaseModel, Field

from app.common.constant import Gender


class RegisterInput(BaseModel):
    """Thông tin gửi lên khi đăng ký tài khoản mới."""

    username: str = Field(min_length=3, max_length=64, description="Tên đăng nhập")
    password: str = Field(min_length=6, max_length=128, description="Mật khẩu")
    full_name: str = Field(min_length=1, max_length=255, description="Họ và tên")
    dob: date = Field(description="Ngày sinh")
    gender: Gender = Field(description="Giới tính (male / female)")


class LoginInput(BaseModel):
    """Thông tin gửi lên khi đăng nhập."""

    username: str = Field(min_length=1, max_length=64, description="Tên đăng nhập")
    password: str = Field(min_length=1, max_length=128, description="Mật khẩu")


class RefreshTokenInput(BaseModel):
    """Thông tin gửi lên khi cần cấp mới access token từ refresh token."""

    refresh_token: str = Field(min_length=1, description="Refresh token JWT")

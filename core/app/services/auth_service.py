"""Service xử lý nghiệp vụ xác thực người dùng: Đăng ký, Đăng nhập, Làm mới token, Đăng xuất."""

from datetime import UTC, datetime

from app.common.constant import Gender
from app.config.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.dto.request.auth import LoginInput, RegisterInput
from app.dto.response.auth import TokenPairOutput, UserSummaryOutput
from app.exception.errors import (
    AuthenticationError,
    UsernameAlreadyExistsError,
)
from app.infra.redis_client import RedisClient
from app.models.patient_profile import PatientProfile
from app.models.user import User
from app.repositories.patient_profile_repository import PatientProfileRepository
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        patient_profile_repo: PatientProfileRepository,
        redis: RedisClient,
    ) -> None:
        self._user_repo = user_repo
        self._patient_profile_repo = patient_profile_repo
        self._redis = redis

    async def register(self, input_data: RegisterInput) -> TokenPairOutput:
        """Đăng ký tài khoản mới:

        1. Kiểm tra username chưa trùng.
        2. Băm mật khẩu và tạo User.
        3. Tự động tạo một PatientProfile mặc định cho chính chủ.
        4. Cấp cặp Access Token và Refresh Token.
        """
        existing = await self._user_repo.get_by_username(input_data.username)
        if existing is not None:
            raise UsernameAlreadyExistsError(
                f"Tên đăng nhập '{input_data.username}' đã được sử dụng."
            )

        hashed_pw = hash_password(input_data.password)
        new_user = User(
            username=input_data.username,
            full_name=input_data.full_name,
            dob=input_data.dob,
            gender=input_data.gender.value,
            password_hash=hashed_pw,
        )
        created_user = await self._user_repo.create(new_user)

        # Tạo hồ sơ bệnh nhân mặc định (chính mình)
        default_profile = PatientProfile(
            user_id=created_user.id,
            full_name=created_user.full_name,
            dob=created_user.dob,
            gender=created_user.gender,
        )
        await self._patient_profile_repo.create(default_profile)

        role = "patient"
        return await self._generate_token_pair(created_user, role)

    async def login(self, input_data: LoginInput) -> TokenPairOutput:
        """Đăng nhập bằng username và mật khẩu."""
        user = await self._user_repo.get_by_username(input_data.username)
        if (
            user is None
            or user.password_hash is None
            or not verify_password(input_data.password, user.password_hash)
        ):
            raise AuthenticationError("Tên đăng nhập hoặc mật khẩu không chính xác.")

        role = await self._user_repo.get_role(user.id)
        return await self._generate_token_pair(user, role)

    async def refresh_token(self, refresh_token_str: str) -> TokenPairOutput:
        """Làm mới Access Token từ Refresh Token hợp lệ (hỗ trợ rotation)."""
        try:
            payload = decode_token(refresh_token_str)
        except Exception as exc:
            raise AuthenticationError("Refresh token không hợp lệ hoặc đã hết hạn.") from exc

        if payload.get("type") != "refresh":
            raise AuthenticationError("Loại token không hợp lệ.")

        user_id = payload.get("sub")
        jti = payload.get("jti")
        if not user_id or not jti:
            raise AuthenticationError("Token thiếu thông tin định danh.")

        redis_key = f"auth:refresh:{user_id}:{jti}"
        is_valid = await self._redis.get(redis_key)
        if not is_valid:
            raise AuthenticationError("Refresh token đã bị thu hồi hoặc đã hết hạn.")

        # Thu hồi refresh token cũ (rotation)
        await self._redis.delete(redis_key)

        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("Không tìm thấy tài khoản người dùng.")

        role = await self._user_repo.get_role(user.id)
        return await self._generate_token_pair(user, role)

    async def logout(self, refresh_token_str: str) -> None:
        """Thu hồi Refresh Token trong Redis khi người dùng đăng xuất."""
        try:
            payload = decode_token(refresh_token_str)
            if payload.get("type") == "refresh":
                user_id = payload.get("sub")
                jti = payload.get("jti")
                if user_id and jti:
                    await self._redis.delete(f"auth:refresh:{user_id}:{jti}")
        except Exception:
            # Bỏ qua lỗi decode lúc logout (token đã hỏng hoặc hết hạn)
            pass

    async def get_current_account(self, user_id: str) -> UserSummaryOutput:
        """Lấy thông tin tài khoản hiện tại."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("Không tìm thấy tài khoản người dùng.")

        role = await self._user_repo.get_role(user.id)
        return UserSummaryOutput(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            dob=user.dob,
            gender=Gender(user.gender),
            role=role,
        )

    async def _generate_token_pair(self, user: User, role: str) -> TokenPairOutput:
        """Sinh Access Token và Refresh Token, lưu Refresh Token vào Redis."""
        access_token = create_access_token(
            user_id=user.id, role=role, username=user.username
        )
        refresh_token_str, jti, exp = create_refresh_token(user_id=user.id)

        # Lưu jti vào Redis với TTL tương ứng thời gian sống còn lại
        now_epoch = int(datetime.now(UTC).timestamp())
        ttl_seconds = max(1, exp - now_epoch)
        await self._redis.set_value(
            f"auth:refresh:{user.id}:{jti}", "1", ex_seconds=ttl_seconds
        )

        return TokenPairOutput(
            access_token=access_token,
            refresh_token=refresh_token_str,
            user=UserSummaryOutput(
                id=user.id,
                username=user.username,
                full_name=user.full_name,
                dob=user.dob,
                gender=Gender(user.gender),
                role=role,
            ),
        )

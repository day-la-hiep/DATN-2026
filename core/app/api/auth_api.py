"""Router API cho các tác vụ xác thực: Đăng ký, Đăng nhập, Làm mới token, Đăng xuất, Lấy thông tin cá nhân."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service, get_current_user
from app.dto.common import ApiResponse
from app.dto.request.auth import LoginInput, RefreshTokenInput, RegisterInput
from app.dto.response.auth import TokenPairOutput, UserSummaryOutput
from app.models.user import User
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TokenPairOutput],
    operation_id="registerUser",
)
async def register(
    body: RegisterInput,
    service: AuthServiceDep,
) -> ApiResponse[TokenPairOutput]:
    """Đăng ký tài khoản người dùng mới (tự động tạo hồ sơ bệnh nhân chính chủ) và trả về cặp Token."""
    result = await service.register(body)
    return ApiResponse(data=result)


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TokenPairOutput],
    operation_id="loginUser",
)
async def login(
    body: LoginInput,
    service: AuthServiceDep,
) -> ApiResponse[TokenPairOutput]:
    """Đăng nhập bằng username và mật khẩu, trả về Access Token + Refresh Token."""
    result = await service.login(body)
    return ApiResponse(data=result)


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[TokenPairOutput],
    operation_id="refreshToken",
)
async def refresh_token(
    body: RefreshTokenInput,
    service: AuthServiceDep,
) -> ApiResponse[TokenPairOutput]:
    """Cấp lại Access Token và Refresh Token mới (Token Rotation)."""
    result = await service.refresh_token(body.refresh_token)
    return ApiResponse(data=result)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[dict[str, str]],
    operation_id="logoutUser",
)
async def logout(
    body: RefreshTokenInput,
    service: AuthServiceDep,
) -> ApiResponse[dict[str, str]]:
    """Đăng xuất và thu hồi Refresh Token trên Redis."""
    await service.logout(body.refresh_token)
    return ApiResponse(data={"message": "Đăng xuất thành công."})


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[UserSummaryOutput],
    operation_id="getCurrentAccount",
)
async def get_current_account(
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> ApiResponse[UserSummaryOutput]:
    """Lấy thông tin tài khoản của người dùng đang đăng nhập."""
    user_info = await service.get_current_account(current_user.id)
    return ApiResponse(data=user_info)

"""Lỗi nghiệp vụ dùng chung"""


class AppError(Exception):
    """Gốc của mọi lỗi nghiệp vụ — thông báo hiển thị nguyên văn cho người dùng."""

    status_code = 400


class NotFoundError(AppError):
    """Không tìm thấy đối tượng được yêu cầu (sách, bước, trang...)."""

    status_code = 404


class ConflictError(AppError):
    """Thao tác không hợp lệ ở trạng thái hiện tại (đang chạy, chưa duyệt bước trước...)."""

    status_code = 409


class InvalidError(AppError):
    """Dữ liệu người dùng gửi lên sai."""

    status_code = 422


class PipelineError(ConflictError):
    """Lỗi điều khiển pipeline (sai bước, chưa đủ điều kiện chạy...)."""


class AuthenticationError(AppError):
    """Xác thực thất bại (sai thông tin đăng nhập, token không hợp lệ hoặc đã hết hạn)."""

    status_code = 401


class ForbiddenError(AppError):
    """Không có quyền truy cập tài nguyên hoặc thao tác này."""

    status_code = 403


class UsernameAlreadyExistsError(ConflictError):
    """Tên đăng nhập đã tồn tại trong hệ thống."""

    status_code = 409

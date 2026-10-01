"""Lỗi nghiệp vụ dùng chung. Service chỉ `raise` các lỗi này (không biết HTTP); mã trạng thái
và định dạng response do `exception_handler.py` quyết định."""


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

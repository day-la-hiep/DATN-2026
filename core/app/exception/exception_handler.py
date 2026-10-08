"""Đăng ký handler lỗi cho FastAPI"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exception.errors import AppError, NotFoundError
from pipeline.document_ingest.profile import ProfileError


def _json(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    detail = f"Không tìm thấy: {exc}" if isinstance(exc, NotFoundError) else str(exc)
    return _json(exc.status_code, detail)


async def profile_error_handler(_: Request, exc: ProfileError) -> JSONResponse:
    """Cài đặt (`books.profile`) của sách sai — lỗi dữ liệu người dùng nhập."""
    return _json(422, str(exc))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # pyright: ignore[reportArgumentType]
    app.add_exception_handler(ProfileError, profile_error_handler)  # pyright: ignore[reportArgumentType]

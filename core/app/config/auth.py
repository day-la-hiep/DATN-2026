"""Auth ĐƠN GIẢN kiểu shared-token"""

from fastapi import HTTPException, Request

from app.config.settings import settings


async def require_app_token(request: Request) -> None:
    if not settings.APP_ACCESS_TOKEN:
        return

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if token != settings.APP_ACCESS_TOKEN:
        raise HTTPException(
            status_code=401, detail="Thiếu hoặc sai access token."
        )

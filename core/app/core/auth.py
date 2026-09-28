"""Auth ĐƠN GIẢN kiểu shared-token — dùng khi deploy bản demo cho người ngoài test
(bạn bè, reviewer...), KHÔNG phải hệ thống user auth thật (không user/password/JWT/
session, không phân quyền). 1 token tĩnh duy nhất cho toàn bộ app.

Bật/tắt qua `settings.APP_ACCESS_TOKEN` (`.env`) — rỗng = tắt hoàn toàn, mọi request đi
qua bình thường (mặc định dev, không phá luồng hiện có khi chưa cấu hình). Set giá trị
để bật: mọi request phải kèm header `Authorization: Bearer <token>` khớp giá trị đó.

Áp dụng bằng `dependencies=[Depends(require_app_token)]` ở router (xem `main.py`) —
không áp cho `health.py` (health-check không cần token, vd để uptime monitor gọi được).
"""
from fastapi import HTTPException, Request

from app.core.config import settings


async def require_app_token(request: Request) -> None:
    if not settings.APP_ACCESS_TOKEN:
        return

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if token != settings.APP_ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai access token.")

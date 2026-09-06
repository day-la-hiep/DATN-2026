"""Sinh id cho các entity — tiền tố theo resource để dễ đọc log/debug.

Dùng `uuid4` (không phải UUIDv7/ULID khuyến nghị ở `docs/db-diagram.md` mục 3) —
tài liệu đó ghi rõ đây là khuyến nghị, chưa bắt buộc; đổi sau không ảnh hưởng caller
vì id vẫn là `str`.
"""
import uuid


def new_user_id() -> str:
    return f"user-{uuid.uuid4()}"


def new_conversation_id() -> str:
    return f"conv-{uuid.uuid4()}"


def new_message_id() -> str:
    return f"msg-{uuid.uuid4()}"

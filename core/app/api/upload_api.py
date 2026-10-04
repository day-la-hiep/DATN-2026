"""Upload ảnh đính kèm tin nhắn — dùng làm input cho
`agent/tools/skin_image_classifier.py` (phân loại bệnh da liễu qua ảnh). Endpoint
tách biệt khỏi `conversation_api.py`: FE upload TRƯỚC, nhận lại `FileDto`
(có `storage_key`/`url`), rồi gửi nguyên object đó trong `SendMessageInput.attached_files` khi
`POST /conversations/{id}/messages` (mục 2.1, `docs/api-doc.md`). File được ghi vào bảng `files`.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.deps import get_message_service
from app.dto.common import FileDto
from app.services.message_service import MessageService

router = APIRouter(tags=["uploads"])


@router.post("/uploads", response_model=FileDto, operation_id="uploadAttachment")
async def upload_attachment(
    file: UploadFile, messages: Annotated[MessageService, Depends(get_message_service)]
) -> FileDto:
    try:
        return await messages.upload_attachment(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

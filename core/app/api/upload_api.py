"""Upload ảnh đính kèm tin nhắn — dùng làm input cho
`app/agent/tools/skin_image_classifier.py` (phân loại bệnh da liễu qua ảnh). Endpoint
tách biệt khỏi `conversation_api.py`: FE upload TRƯỚC, nhận lại `FileAttachmentDto`
(có `id`/`url`), rồi gửi nguyên object đó trong `SendMessageInput.attachments` khi
`POST /conversations/{id}/messages` (mục 2.1, `docs/api-doc.md`).
"""
from fastapi import APIRouter, HTTPException, UploadFile

from app.dto.message import FileAttachmentDto
from app.infra.file_storage import save_upload

router = APIRouter(tags=["uploads"])


@router.post("/uploads", response_model=FileAttachmentDto, operation_id="uploadAttachment")
async def upload_attachment(file: UploadFile) -> FileAttachmentDto:
    try:
        result = await save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileAttachmentDto.model_validate(dict(result))

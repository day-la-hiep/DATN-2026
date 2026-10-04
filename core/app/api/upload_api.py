"""Upload ảnh đính kèm tin nhắn — dùng làm input cho
`agent/tools/skin_image_classifier.py` (phân loại bệnh da liễu qua ảnh). Endpoint
tách biệt khỏi `conversation_api.py`: FE upload TRƯỚC, nhận lại `FileDto`
(có `storageKey`/`url`), rồi gửi nguyên object đó trong `SendMessageInput.attachedFiles` khi
`POST /conversations/{id}/messages` (mục 2.1, `docs/api-doc.md`).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.deps import get_file_store_service
from app.dto.common import FileDto
from app.services.file_store_service import FileStoreService

router = APIRouter(tags=["uploads"])


@router.post("/uploads", response_model=FileDto, operation_id="uploadAttachment")
async def upload_attachment(
    file: UploadFile, attachments: Annotated[FileStoreService, Depends(get_file_store_service)]
) -> FileDto:
    try:
        result = await attachments.save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileDto(file_name=result["name"], storage_key=result["id"], content_type=result["type"],
                   size=result["size"], url=result["url"])

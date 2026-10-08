"""Upload ảnh đính kèm tin nhắn"""
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

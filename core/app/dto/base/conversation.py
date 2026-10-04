from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, model_validator

from app.common.constant import MessageType
from app.dto.base.medical import SupportRequest
from app.dto.base.user import Doctor, PatienProfile
from app.dto.base.video_call import VideoCall


class Conversation(BaseModel):
    patient: PatienProfile
    doctor: Doctor
    message: list[Message]


class Message(BaseModel):
    content: str
    metadata: MessageMetadata


class MessageMetadata(BaseModel):
    message_type: MessageType
    attached_file: list[DocumentSource]
    support_request: SupportRequest | None
    video_call: VideoCall | None

    @model_validator(mode="after")
    def validate_metadata(self):
        if self.message_type == MessageType.SUPPORT_REQUEST:
            if self.support_request is None:
                raise ValueError(
                    "support_request is required for SUPPORT_REQUEST"
                )
        if self.message_type == MessageType.VIDEO_CALL:
            if self.video_call is None:
                raise ValueError("video_call is require for VIDEO_CALL")

        return self


class DocumentSource(BaseModel):
    file_name: str
    content_type: str
    size: int
    uploaded_time: datetime
    storage_key: str

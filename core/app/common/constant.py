from enum import Enum


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


class MessageType(str, Enum):
    TEXT = "text"
    VIDEO_CALL = "video_call"
    SUPPORT_REQUEST = "support"
    ATTACHED = "attached"

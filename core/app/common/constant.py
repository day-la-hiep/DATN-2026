from enum import Enum


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


class MessageType(str, Enum):
    TEXT = "text"
    VIDEO_CALL = "video_call"
    ATTACHED = "attached"
    # 3 mốc của một phiên tư vấn bác sĩ, hiện trong luồng chat như tin hệ thống
    CONSULTATION_REQUESTED = "consultation_requested"  # bệnh nhân gửi yêu cầu
    CONSULTATION_ACCEPTED = "consultation_accepted"  # bác sĩ nhận và bắt đầu xử lý
    CONSULTATION_RESOLVED = "consultation_resolved"  # bác sĩ đóng yêu cầu khi xong


class MessageSender(str, Enum):
    """Ai gửi tin. Bác sĩ trả lời ngay trong luồng chat của hội thoại, nên tin phải phân biệt được 3 bên."""

    PATIENT = "patient"
    AI = "ai"
    DOCTOR = "doctor"


class ConsultationStatus(str, Enum):
    PENDING = "pending"  # chờ bác sĩ nhận
    ACTIVE = "active"  # bác sĩ đang trao đổi
    RESOLVED = "resolved"  # bác sĩ đã đánh dấu xử lý xong

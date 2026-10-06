"""DTO dùng chung cho nhiều resource — phần dẫn xuất từ entity chuẩn `app/dto/base/` (file, bác sĩ / phiên rút gọn) và
envelope response. DTO chỉ riêng một resource đặt ở `app/dto/request|response/`."""
from app.dto.common.chat import AnsweredChoice, ChoiceOption, MessageChoice, Source, Step
from app.dto.common.consultation import ConsultationSessionDto, DoctorDto
from app.dto.common.envelope import ApiResponse
from app.dto.common.file import FileDto

__all__ = [
    "AnsweredChoice", "ApiResponse", "ChoiceOption", "ConsultationSessionDto", "DoctorDto", "FileDto", "MessageChoice",
    "Source", "Step",
]

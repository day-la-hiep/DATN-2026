"""API endpoints cho Bác sĩ & Báo cáo tư vấn."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_consultation_service
from app.dto.common import ApiResponse
from app.dto.consultation import (
    ConsultationSessionOutput,
    DoctorReplyInput,
    RequestConsultationInput,
)
from app.dto.response.message import MessageOutput
from app.services.consultation_service import ConsultationService

router = APIRouter(tags=["doctor"])

ConsultationServiceDep = Annotated[
    ConsultationService, Depends(get_consultation_service)
]


@router.get(
    "/doctor/consultations",
    response_model=ApiResponse[list[ConsultationSessionOutput]],
    operation_id="listDoctorConsultations",
)
async def list_consultations(
    service: ConsultationServiceDep,
    status: Annotated[str | None, Query()] = None,
) -> ApiResponse[list[ConsultationSessionOutput]]:
    """Lấy danh sách các phiên tư vấn cho bác sĩ theo dõi."""
    sessions = await service.list_sessions(status)
    return ApiResponse(data=sessions)


@router.get(
    "/doctor/consultations/{session_id}",
    response_model=ApiResponse[ConsultationSessionOutput],
    operation_id="getDoctorConsultation",
)
async def get_consultation(
    session_id: str,
    service: ConsultationServiceDep,
) -> ApiResponse[ConsultationSessionOutput]:
    """Lấy chi tiết một phiên tư vấn (kèm dữ kiện lâm sàng và báo cáo AI kết luận)."""
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy phiên tư vấn id={session_id}",
        )
    return ApiResponse(data=session)


@router.post(
    "/doctor/consultations/{session_id}/accept",
    response_model=ApiResponse[ConsultationSessionOutput],
    operation_id="acceptDoctorConsultation",
)
async def accept_consultation(
    session_id: str,
    service: ConsultationServiceDep,
) -> ApiResponse[ConsultationSessionOutput]:
    """Bác sĩ tiếp quản ca tư vấn (chuyển status sang active)."""
    try:
        session = await service.accept_session(session_id)
        return ApiResponse(data=session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/doctor/consultations/{session_id}/resolve",
    response_model=ApiResponse[ConsultationSessionOutput],
    operation_id="resolveDoctorConsultation",
)
async def resolve_consultation(
    session_id: str,
    service: ConsultationServiceDep,
) -> ApiResponse[ConsultationSessionOutput]:
    """Bác sĩ đóng phiên tư vấn (chuyển status sang resolved)."""
    try:
        session = await service.resolve_session(session_id)
        return ApiResponse(data=session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/conversations/{conversation_id}/request-consultation",
    response_model=ApiResponse[ConsultationSessionOutput],
    operation_id="requestConsultation",
)
async def request_consultation(
    conversation_id: str,
    body: RequestConsultationInput,
    service: ConsultationServiceDep,
) -> ApiResponse[ConsultationSessionOutput]:
    """Bệnh nhân yêu cầu kết nối Bác sĩ -> Tự động kích hoạt LLM sinh báo cáo tiền tư vấn AI."""
    session = await service.request_consultation(
        conversation_id, body.reason or "Bệnh nhân yêu cầu bác sĩ tư vấn"
    )
    return ApiResponse(data=session)


@router.post(
    "/doctor/consultations/{session_id}/reply",
    response_model=ApiResponse[MessageOutput],
    operation_id="replyDoctorConsultation",
)
async def reply_consultation(
    session_id: str,
    body: DoctorReplyInput,
    service: ConsultationServiceDep,
) -> ApiResponse[MessageOutput]:
    """Bác sĩ gửi tin nhắn phản hồi tới bệnh nhân trong phiên tư vấn."""
    try:
        msg = await service.send_doctor_reply(session_id, body.content)
        return ApiResponse(data=msg)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

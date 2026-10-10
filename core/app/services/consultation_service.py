"""Nghiệp vụ Tư vấn & Báo cáo tiền tư vấn (Pre-consultation Report Generation)."""
import json
import logging
import uuid
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from agent.common.llm import get_model
from app.common.constant import MessageSender, MessageType
from app.dto.consultation import (
    ClinicalFactOutput,
    ConsultationSessionOutput,
    PatientProfileDto,
    PreConsultationReportOutput,
)
from app.dto.response.message import MessageOutput
from app.exception.errors import ForbiddenError, NotFoundError
from app.models.clinical import (
    ClinicalFact,
    PreConsultationReport,
)
from app.models.consultation_session import ConsultationSession
from app.models.message import Message
from app.models.patient_profile import PatientProfile
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """Bạn là trợ lý y khoa chuyên sâu da liễu.
Nhiệm vụ của bạn là đọc toàn bộ đoạn hội thoại giữa bệnh nhân và trợ lý AI, sau đó:
1. Rút trích các DỮ KIỆN LÂM SÀNG (clinical facts) có cấu trúc.
2. Soạn một BÁO CÁO TIỀN TƯ VẤN (Pre-consultation Report) súc tích, chuyên nghiệp cho Bác sĩ da liễu đọc trước khi nhận ca.

BẮT BUỘC TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON SAU (không kèm markdown code block hoặc text thừa):
{
  "facts": [
    {
      "template_label": "Tên chuẩn của triệu chứng/tổn thương/thuốc",
      "fact_type": "symptom | lesion | history | medication | allergy | image_finding | other",
      "detail": "Mô tả chi tiết cụ thể của bệnh nhân"
    }
  ],
  "summary": "Nội dung tóm tắt lâm sàng (định dạng Markdown)"
}

Yêu cầu cho phần `summary` (dùng Markdown đẹp):
- ## Lý do khám & Bệnh sử: Tóm tắt triệu chứng chính, thời gian khởi phát.
- ## Vị trí & Đặc điểm tổn thương: Mô tả hình thái, vị trí vùng da bị bệnh.
- ## Đánh giá sơ bộ của AI: 1–3 bệnh nghi ngờ xếp theo độ phù hợp, độ tin cậy (Cao/Vừa/Thấp).
- ## Dấu hiệu cờ đỏ (Red Flags): Đã kiểm tra loại trừ hay nghi ngờ có cờ đỏ gì.
- ## Đề xuất cho Bác sĩ tiếp quản: Gợi ý câu hỏi lâm sàng cần làm rõ hoặc cận lâm sàng nên chỉ định.
- Lưu ý: Ghi rõ 'Kết luận AI chỉ mang tính chất tham khảo hỗ trợ tiền lâm sàng' ở cuối.
"""


class ConsultationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ConsultationRepository(db)
        self._conv_repo = ConversationRepository(db)
        self._msg_repo = MessageRepository(db)

    def _to_output(
        self,
        session: ConsultationSession,
        conv_title: str = "Hội thoại tư vấn",
        report: PreConsultationReport | None = None,
        facts: list[ClinicalFactOutput] | None = None,
        patient: PatientProfileDto | None = None,
    ) -> ConsultationSessionOutput:
        patient_dto = patient or PatientProfileDto(id="", full_name="Bệnh nhân", dob="", gender="male")

        report_dto = None
        if report:
            report_dto = PreConsultationReportOutput(
                id=report.id,
                summary=report.summary,
                created_at=report.created_at.isoformat(),
            )

        return ConsultationSessionOutput(
            id=session.id,
            conversation_id=session.conversation_id,
            conversation_title=conv_title,
            patient=patient_dto,
            doctor_id=session.doctor_id,
            status=session.status,
            reason=session.reason or "Bệnh nhân yêu cầu bác sĩ tư vấn",
            requested_at=session.requested_at.isoformat(),
            started_at=session.started_at.isoformat() if session.started_at else None,
            resolved_at=session.resolved_at.isoformat() if session.resolved_at else None,
            report=report_dto,
            clinical_facts=facts or [],
        )

    async def _patient_dto(self, patient_profile_id: str | None) -> PatientProfileDto | None:
        profile = await self._db.get(PatientProfile, patient_profile_id) if patient_profile_id else None
        if profile is None:
            return None
        return PatientProfileDto(
            id=profile.id, full_name=profile.full_name, dob=profile.dob.isoformat(), gender=profile.gender
        )

    async def _owned_session(self, session_id: str, doctor_id: str) -> ConsultationSession:
        session = await self._repo.get_session(session_id)
        if session is None:
            raise NotFoundError(f"Không tìm thấy phiên tư vấn id={session_id}")
        if session.doctor_id not in (None, doctor_id):
            raise ForbiddenError("Ca tư vấn này đang do bác sĩ khác phụ trách.")
        return session

    async def list_sessions(
        self, status: str | None = None, doctor_id: str | None = None
    ) -> list[ConsultationSessionOutput]:
        sessions = await self._repo.list_sessions(status, doctor_id)
        results: list[ConsultationSessionOutput] = []
        for s in sessions:
            conv = await self._conv_repo.get(s.conversation_id)
            title = conv.title if conv else "Hội thoại da liễu"
            report = await self._repo.get_report(s.id)
            facts_dto: list[ClinicalFactOutput] = []
            if conv and conv.patient_profile_id:
                raw_facts = await self._repo.get_clinical_facts_by_patient(conv.patient_profile_id)
                facts_dto = [
                    ClinicalFactOutput(
                        id=f.id,
                        template_label=tpl.label,
                        fact_type=tpl.fact_type,
                        detail=f.detail,
                        status=f.status,
                        created_at=f.created_at.isoformat(),
                    )
                    for f, tpl in raw_facts
                ]
            patient = await self._patient_dto(conv.patient_profile_id if conv else None)
            results.append(self._to_output(s, title, report, facts_dto, patient))
        return results

    async def get_session(
        self, session_id: str, doctor_id: str
    ) -> ConsultationSessionOutput | None:
        session = await self._owned_session(session_id, doctor_id)
        conv = await self._conv_repo.get(session.conversation_id)
        title = conv.title if conv else "Hội thoại da liễu"
        report = await self._repo.get_report(session.id)
        facts_dto: list[ClinicalFactOutput] = []
        if conv and conv.patient_profile_id:
            raw_facts = await self._repo.get_clinical_facts_by_patient(conv.patient_profile_id)
            facts_dto = [
                ClinicalFactOutput(
                    id=f.id,
                    template_label=tpl.label,
                    fact_type=tpl.fact_type,
                    detail=f.detail,
                    status=f.status,
                    created_at=f.created_at.isoformat(),
                )
                for f, tpl in raw_facts
            ]
        patient = await self._patient_dto(conv.patient_profile_id if conv else None)
        return self._to_output(session, title, report, facts_dto, patient)

    async def accept_session(
        self, session_id: str, doctor_id: str
    ) -> ConsultationSessionOutput:
        session = await self._owned_session(session_id, doctor_id)
        session = await self._repo.accept_session(session, doctor_id)
        conv = await self._conv_repo.get(session.conversation_id)
        report = await self._repo.get_report(session.id)
        patient = await self._patient_dto(conv.patient_profile_id if conv else None)
        return self._to_output(session, conv.title if conv else "Hội thoại", report, patient=patient)

    async def resolve_session(
        self, session_id: str, doctor_id: str
    ) -> ConsultationSessionOutput:
        session = await self._owned_session(session_id, doctor_id)
        session = await self._repo.resolve_session(session)
        conv = await self._conv_repo.get(session.conversation_id)
        report = await self._repo.get_report(session.id)
        patient = await self._patient_dto(conv.patient_profile_id if conv else None)
        return self._to_output(session, conv.title if conv else "Hội thoại", report, patient=patient)

    async def request_consultation(
        self, conversation_id: str, user_id: str, reason: str = "Bệnh nhân yêu cầu bác sĩ tư vấn"
    ) -> ConsultationSessionOutput:
        """Kích hoạt tạo phiên tư vấn & gọi LLM sinh báo cáo tiền tư vấn AI."""
        conv = await self._conv_repo.get(conversation_id)
        if conv is None:
            raise NotFoundError("Không tìm thấy hội thoại.")
        if await self._conv_repo.owner_user_id(conv) != user_id:
            raise ForbiddenError("Bạn chỉ có thể yêu cầu bác sĩ cho hội thoại của chính mình.")
        patient = await self._patient_dto(conv.patient_profile_id)

        # 1. Kiểm tra nếu đã có phiên đang mở thì trả về luôn
        existing = await self._repo.get_open_session_by_conversation(conversation_id)
        conv_title = conv.title
        if existing:
            rep = await self._repo.get_report(existing.id)
            return self._to_output(existing, conv_title, rep, patient=patient)

        # 2. Tạo session mới
        session_id = f"cs-{uuid.uuid4()}"
        session = ConsultationSession(
            id=session_id,
            conversation_id=conversation_id,
            status="pending",
            reason=reason,
            requested_at=datetime.now(UTC),
        )
        await self._repo.create_session(session)

        # 3. Lấy lịch sử hội thoại để nạp vào LLM
        messages = await self._msg_repo.list_by_conversation(conversation_id)
        chat_transcript = "\n".join(
            f"[{m.sender.upper()}]: {m.content}" for m in messages if m.content
        )

        # 4. Gọi LLM sinh báo cáo & bóc tách dữ kiện lâm sàng
        facts_to_save: list[ClinicalFact] = []
        facts_dto: list[ClinicalFactOutput] = []
        summary_text = ""
        patient_profile_id = conv.patient_profile_id

        try:
            llm = get_model()
            prompt = [
                SystemMessage(content=REPORT_SYSTEM_PROMPT),
                HumanMessage(
                    content=f"Đoạn hội thoại giữa bệnh nhân và AI:\n\n{chat_transcript}\n\nHãy sinh báo cáo JSON:"
                ),
            ]
            response = await llm.ainvoke(prompt)
            raw_content = response.content
            if isinstance(raw_content, list):
                raw_content = "\n".join(str(c) for c in raw_content)

            # Làm sạch JSON nếu model bọc trong ```json
            cleaned = str(raw_content).strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()

            parsed = json.loads(cleaned)
            summary_text = parsed.get("summary", "")
            raw_facts = parsed.get("facts", [])

            for rf in raw_facts:
                f_type = rf.get("fact_type", "symptom")
                f_label = rf.get("template_label", "Dữ kiện lâm sàng")
                f_detail = rf.get("detail", "")
                tpl = await self._repo.get_or_create_template(f_type, f_label)
                fact_id = f"cf-{uuid.uuid4()}"
                now = datetime.now(UTC)
                facts_to_save.append(
                    ClinicalFact(
                        id=fact_id,
                        patient_profile_id=patient_profile_id,
                        template_id=tpl.id,
                        detail=f_detail,
                        status="active",
                        created_at=now,
                    )
                )
                facts_dto.append(
                    ClinicalFactOutput(
                        id=fact_id,
                        template_label=tpl.label,
                        fact_type=tpl.fact_type,
                        detail=f_detail,
                        status="active",
                        created_at=now.isoformat(),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lỗi khi gọi LLM sinh báo cáo: %s", exc)
            summary_text = (
                f"## Tóm tắt phiên tư vấn\n"
                f"- **Lý do khám**: {reason}\n"
                f"- **Ghi nhận**: Bệnh nhân yêu cầu bác sĩ tư vấn trực tiếp.\n"
                f"- *Hệ thống đang đồng bộ dữ kiện lâm sàng.*"
            )

        # 5. Lưu Report và Facts
        report = PreConsultationReport(
            id=f"rep-{uuid.uuid4()}",
            consultation_session_id=session_id,
            summary=summary_text,
            created_at=datetime.now(UTC),
        )
        await self._repo.create_report(report)
        if facts_to_save:
            await self._repo.add_clinical_facts(facts_to_save)

        return self._to_output(session, conv_title, report, facts_dto, patient)

    async def send_doctor_reply(
        self, session_id: str, content: str, doctor_id: str
    ) -> MessageOutput:
        """Bác sĩ phản hồi bệnh nhân trong phiên tư vấn."""
        session = await self._owned_session(session_id, doctor_id)

        # Tự động tiếp nhận ca nếu chưa active
        if session.status == "pending":
            await self._repo.accept_session(session, doctor_id)

        msg_id = f"msg-{uuid.uuid4()}"
        now = datetime.now(UTC)
        msg = Message(
            id=msg_id,
            conversation_id=session.conversation_id,
            sender=MessageSender.DOCTOR.value,
            message_type=MessageType.TEXT.value,
            content=content,
            status="done",
            extra={"doctorId": doctor_id},
            created_at=now,
        )
        await self._msg_repo.create(msg)

        # Broadcast event qua Redis Pub/Sub để client SSE nhận được realtime
        try:
            from app.api.deps import get_redis_client
            from app.config.constants import AGENT_EVENTS_CHANNEL
            redis = get_redis_client()
            channel = AGENT_EVENTS_CHANNEL.format(conversation_id=session.conversation_id)
            event_payload = json.dumps({
                "type": "message.done",
                "messageId": msg_id,
                "sender": MessageSender.DOCTOR.value,
                "content": content,
            })
            await redis.publish(channel, event_payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Không thể publish event bác sĩ qua Redis: %s", exc)

        return MessageOutput(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender=MessageSender.DOCTOR,
            content=msg.content,
            status="done",
            created_at=msg.created_at.isoformat(),
        )

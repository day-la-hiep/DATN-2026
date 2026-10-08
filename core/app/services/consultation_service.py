"""Nghiệp vụ Tư vấn & Báo cáo tiền tư vấn (Pre-consultation Report Generation)."""
import json
import logging
from datetime import UTC, datetime

from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from agent.llm import get_model
from app.config.ids import (
    new_clinical_fact_id,
    new_consultation_session_id,
    new_message_id,
    new_report_id,
)
from app.dto.consultation import (
    ClinicalFactOutput,
    ConsultationSessionOutput,
    PatientProfileDto,
    PreConsultationReportOutput,
)
from app.dto.message import MessageOutput
from app.models.consultation import (
    ClinicalFact,
    ConsultationSession,
    PreConsultationReport,
)
from app.models.message import Message
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
        self, session: ConsultationSession, conv_title: str = "Hội thoại tư vấn"
    ) -> ConsultationSessionOutput:
        # Mock profile mặc định (vì đồ án chưa có bảng auth/profiles hoàn chỉnh)
        patient_dto = PatientProfileDto(
            id="p-default",
            full_name="Nguyễn Văn A",
            dob="1998-05-12",
            gender="male",
        )

        report_dto = None
        if session.report:
            report_dto = PreConsultationReportOutput(
                id=session.report.id,
                summary=session.report.summary,
                created_at=session.report.created_at.isoformat(),
            )

        facts_dto = [
            ClinicalFactOutput(
                id=f.id,
                template_label=f.template_label,
                fact_type=f.fact_type,
                detail=f.detail,
                status=f.status,
                created_at=f.created_at.isoformat(),
            )
            for f in session.clinical_facts
        ]

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
            clinical_facts=facts_dto,
        )

    async def list_sessions(
        self, status: str | None = None
    ) -> list[ConsultationSessionOutput]:
        sessions = await self._repo.list_sessions(status)
        results: list[ConsultationSessionOutput] = []
        for s in sessions:
            conv = await self._conv_repo.get(s.conversation_id)
            title = conv.title if conv else "Hội thoại da liễu"
            results.append(self._to_output(s, title))
        return results

    async def get_session(
        self, session_id: str
    ) -> ConsultationSessionOutput | None:
        session = await self._repo.get_session(session_id)
        if not session:
            return None
        conv = await self._conv_repo.get(session.conversation_id)
        title = conv.title if conv else "Hội thoại da liễu"
        return self._to_output(session, title)

    async def accept_session(
        self, session_id: str, doctor_id: str = "doc-default"
    ) -> ConsultationSessionOutput:
        session = await self._repo.get_session(session_id)
        if not session:
            raise ValueError(f"Không tìm thấy phiên tư vấn id={session_id}")
        session = await self._repo.accept_session(session, doctor_id)
        conv = await self._conv_repo.get(session.conversation_id)
        return self._to_output(session, conv.title if conv else "Hội thoại")

    async def resolve_session(
        self, session_id: str
    ) -> ConsultationSessionOutput:
        session = await self._repo.get_session(session_id)
        if not session:
            raise ValueError(f"Không tìm thấy phiên tư vấn id={session_id}")
        session = await self._repo.resolve_session(session)
        conv = await self._conv_repo.get(session.conversation_id)
        return self._to_output(session, conv.title if conv else "Hội thoại")

    async def request_consultation(
        self, conversation_id: str, reason: str = "Bệnh nhân yêu cầu bác sĩ tư vấn"
    ) -> ConsultationSessionOutput:
        """Kích hoạt tạo phiên tư vấn & gọi LLM sinh báo cáo tiền tư vấn AI."""
        # 1. Kiểm tra nếu đã có phiên đang mở thì trả về luôn
        existing = await self._repo.get_open_session_by_conversation(conversation_id)
        conv = await self._conv_repo.get(conversation_id)
        conv_title = conv.title if conv else "Hội thoại da liễu"
        if existing:
            return self._to_output(existing, conv_title)

        # 2. Tạo session mới
        session_id = new_consultation_session_id()
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
            f"[{m.role.upper()}]: {m.content}" for m in messages if m.content
        )

        # 4. Gọi LLM sinh báo cáo & bóc tách dữ kiện lâm sàng
        facts_to_save: list[ClinicalFact] = []
        summary_text = ""

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
                facts_to_save.append(
                    ClinicalFact(
                        id=new_clinical_fact_id(),
                        consultation_session_id=session_id,
                        template_label=rf.get("template_label", "Dữ kiện lâm sàng"),
                        fact_type=rf.get("fact_type", "symptom"),
                        detail=rf.get("detail", ""),
                        status="active",
                        created_at=datetime.now(UTC),
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
            id=new_report_id(),
            consultation_session_id=session_id,
            summary=summary_text,
            created_at=datetime.now(UTC),
        )
        await self._repo.create_report(report)
        if facts_to_save:
            await self._repo.add_clinical_facts(facts_to_save)

        # Lấy lại session đầy đủ quan hệ để serialize
        fresh_session = await self._repo.get_session(session_id)
        if not fresh_session:
            fresh_session = session

        return self._to_output(fresh_session, conv_title)

    async def send_doctor_reply(
        self, session_id: str, content: str, doctor_id: str = "doc-default"
    ) -> MessageOutput:
        """Bác sĩ phản hồi bệnh nhân trong phiên tư vấn."""
        session = await self._repo.get_session(session_id)
        if not session:
            raise ValueError(f"Không tìm thấy phiên tư vấn id={session_id}")

        # Tự động tiếp nhận ca nếu chưa active
        if session.status == "pending":
            await self._repo.accept_session(session, doctor_id)

        msg_id = new_message_id()
        now = datetime.now(UTC)
        msg = Message(
            id=msg_id,
            conversation_id=session.conversation_id,
            role="doctor",
            content=content,
            status="done",
            extra={"sender": "doctor", "doctorId": doctor_id},
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
                "role": "doctor",
                "content": content,
            })
            await redis.publish(channel, event_payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Không thể publish event bác sĩ qua Redis: %s", exc)

        return MessageOutput(
            id=msg.id,
            conversation_id=msg.conversation_id,
            role="doctor",
            content=msg.content,
            status="done",
            created_at=msg.created_at.isoformat(),
        )

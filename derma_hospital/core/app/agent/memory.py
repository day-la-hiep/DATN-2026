"""Long-term memory: sau mỗi turn hoàn tất, tóm tắt (distill) qua 1 lần gọi LLM rồi
lưu vector vào Qdrant; đầu mỗi turn mới, semantic search theo `user_id` để lấy
memory liên quan làm context. Dùng CHUNG 1 cơ chế cho cả trong-hội-thoại lẫn
xuyên-hội-thoại — không phân biệt nguồn gốc, chỉ lọc theo `user_id` + độ liên quan
(xem `core/app/kien-truc-memory.md`).

Nguyên tắc: memory là phụ trợ, KHÔNG được làm hỏng turn chính — mọi lỗi (Qdrant
down, LLM distill lỗi...) chỉ log, không raise.
"""
import uuid
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.agent.llm import get_llm
from app.agent.state import ReasoningResult
from app.infra import qdrant_client

DISTILL_SYSTEM_PROMPT = (
    "Bạn trích xuất trí nhớ dài hạn cho trợ lý tư vấn da liễu. Từ 1 lượt hội thoại, "
    "tóm tắt NGẮN GỌN (tối đa 5 gạch đầu dòng) thông tin nên nhớ cho lần tư vấn sau: "
    "tình trạng da/triệu chứng, tiền sử, thuốc/sản phẩm đã dùng hoặc được khuyến "
    "nghị, dị ứng/ràng buộc. Bỏ qua chào hỏi xã giao. Không có gì đáng nhớ thì trả "
    "về đúng chuỗi rỗng."
)

# Model embedding riêng — dùng chung provider Google với `AGENT_MODEL` (đã có sẵn
# `GOOGLE_API_KEY`), không cần thêm provider mới. `models/text-embedding-004` (cũ)
# đã bị Google khai tử cho API key mới — dùng `gemini-embedding-001` (kiểm tra qua
# `ListModels`, xác nhận hỗ trợ `embedContent`), mặc định 3072 chiều nhưng hỗ trợ
# Matryoshka truncation qua `output_dimensionality` — giới hạn về 768 (khớp
# `EMBEDDING_DIM` ở `app/infra/qdrant_client.py`) để vector gọn hơn.
_EMBEDDING_MODEL = "models/gemini-embedding-001"
_EMBEDDING_DIM = 768  # phải khớp EMBEDDING_DIM ở app/infra/qdrant_client.py
_embeddings = GoogleGenerativeAIEmbeddings(model=_EMBEDDING_MODEL)


async def _embed(text: str) -> list[float]:
    return await _embeddings.aembed_query(text, output_dimensionality=_EMBEDDING_DIM)


def _reasoning_transcript(reasoning: list[ReasoningResult]) -> str:
    """Chuyển toàn bộ Reasoning của 1 turn (LLM musing, câu hỏi/trả lời ask_user, kết
    quả tool) thành text phẳng cho prompt distill."""
    lines: list[str] = []
    for r in reasoning:
        if r.step_type == "tool_ask" and r.choice:
            lines.append(f"Hỏi: {r.choice.question}")
            if r.choice.answered:
                lines.append(f"Trả lời: {r.choice.answered.label}")
        elif r.step_type == "tool_call":
            lines.append(f"[Tool {r.title}] {r.content}")
        elif r.content:
            lines.append(r.content)
    return "\n".join(lines)


async def distill_and_store(
    *,
    user_id: str,
    conversation_id: str,
    message_id: str,
    user_content: str,
    reasoning: list[ReasoningResult],
    answer: str,
) -> None:
    """Gọi SAU khi turn kết thúc thành công (`status="done"`) — KHÔNG gọi cho turn
    tạm dừng chờ `ask_user` (xem `app/agent/worker.py::_drive_graph`)."""
    try:
        prompt = (
            f"Tin nhắn người dùng: {user_content}\n\n"
            f"Diễn biến:\n{_reasoning_transcript(reasoning)}\n\nCâu trả lời cuối: {answer}"
        )
        response = await get_llm().ainvoke(
            [SystemMessage(content=DISTILL_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        summary = response.text.strip()
        if not summary:
            return

        vector = await _embed(summary)
        await qdrant_client.upsert_memory(
            point_id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "summary": summary,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[Memory] distill/store thất bại: {exc}")


async def retrieve_context(*, user_id: str, query_text: str, limit: int = 5) -> str | None:
    """Semantic search memory liên quan `query_text` (tin nhắn mới của user) theo
    `user_id` — trả `None` nếu không có gì liên quan hoặc Qdrant lỗi (KHÔNG chặn turn)."""
    if not query_text.strip():
        return None
    try:
        vector = await _embed(query_text)
        hits = await qdrant_client.search_memories(user_id=user_id, vector=vector, limit=limit)
    except Exception as exc:  # noqa: BLE001
        print(f"[Memory] retrieve thất bại: {exc}")
        return None

    if not hits:
        return None
    # Không tự thêm "- " ở đây — `summary` (do LLM distill) đã tự có gạch đầu dòng
    # riêng của nó (xem DISTILL_SYSTEM_PROMPT), thêm nữa sẽ ra "- -" lặp.
    summaries = [str(hit.payload["summary"]) for hit in hits if hit.payload]
    if not summaries:
        return None
    return (
        "[Thông tin đã biết về người dùng này từ các lần tư vấn trước — tham khảo "
        "nếu liên quan, không nhất thiết phải nhắc lại]\n" + "\n\n".join(summaries)
    )

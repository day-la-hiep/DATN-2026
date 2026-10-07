"""Hằng số/helper dùng chung giữa `pre_diagnosis_graph` và `middleware/*` — module lá (không import
lại `pre_diagnosis_graph`/`chat_graph`/`middleware`) để tránh vòng import."""

import json
import re
from typing import Any, NotRequired

from langchain.agents import AgentState
from pydantic import BaseModel, Field

from app.config.constants import AGENT_EVENTS_CHANNEL
from app.api.deps import get_redis_client

# Tên tool hiển thị cho người dùng khi FE render bước "đang tra cứu ..." (SSE
# `message.tool_result`/`message.thinking`, xem `emit_tool_result`/`emit_reasoning_step`
# bên dưới) — tên hàm tiếng Anh (`ask_user`, `hybrid_retrieval`...) khó hiểu với
# người dùng cuối, map sang nhãn tiếng Việt dễ hiểu. Tool nào quên thêm vào đây thì
# fallback về tên gốc.
TOOL_DISPLAY_NAMES: dict[str, str] = {
    "record_reasoning": "Lập luận",
    "ask_user": "Hỏi lại người dùng",
    "save_memory": "Lưu thông tin ghi nhớ",
    "hybrid_retrieval": "Tra cứu sách giáo khoa và đồ thị tri thức",
    "semantic_search": "Tra cứu sách giáo khoa (theo ngữ nghĩa)",
    "keyword_search": "Tra cứu sách giáo khoa (theo từ khoá)",
    "knowledge_graph_search": "Tra cứu đồ thị tri thức",
    "classify_skin_image": "Phân tích ảnh tổn thương da",
    "search_trusted_web": "Tra cứu nguồn web uy tín",
    "fetch_trusted_page": "Đọc trang web uy tín",
}


async def emit(conversation_id: str, payload: dict[str, Any]) -> None:
    channel = AGENT_EVENTS_CHANNEL.format(conversation_id=conversation_id)
    await get_redis_client().publish(
        channel, json.dumps(payload, ensure_ascii=False, default=str)
    )


# Gemini (`include_thoughts=True`, `llm.py`) mở đầu mỗi đoạn "thinking" bằng 1 dòng tiêu
# đề in đậm dạng markdown (vd "**My Approach to Summarizing Psoriasis**") tóm tắt cả đoạn
# suy nghĩ phía sau — lấy ĐÚNG dòng này làm summary hiển thị thay vì dump nguyên đoạn suy
# nghĩ dài (không tự nhiên/không phù hợp hiển thị cho người dùng cuối).
THINKING_TITLE_RE = re.compile(r"^\*\*(.+?)\*\*")
THINKING_SUMMARY_MAX_LEN = 160


class CriticState(AgentState):
    """`AgentState` mở rộng: đếm số lần critic đã yêu cầu viết lại câu trả lời trong
    CÙNG 1 turn — không dùng reducer (`Annotated[..., operator.add]`) vì mỗi lần cần GHI
    ĐÈ giá trị mới, không cộng dồn qua nhiều turn (field reset ngầm mỗi
    `agent_graph.astream()` mới vì không nằm trong checkpoint theo cách cộng dồn)."""

    critic_retries: NotRequired[int]


MAX_CRITIC_RETRIES = 1
# Số lần tối đa/turn middleware lập luận (`middleware/model.py`) ép model làm lại — hết lượt thì
# CHO QUA (như `MAX_CRITIC_RETRIES`) để không treo turn.
MAX_REASONING_RETRIES = 2


class CriticVerdict(BaseModel):
    approved: bool = Field(
        description="True nếu bản nháp đạt yêu cầu, False nếu cần viết lại"
    )
    feedback: str = Field(
        default="",
        description="Lý do từ chối + điều cần sửa — để trống nếu approved=true",
    )

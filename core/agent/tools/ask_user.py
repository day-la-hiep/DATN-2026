"""Tool `ask_user` — hỏi lại người dùng khi agent thiếu thông tin.

Dùng THẲNG `langgraph.types.interrupt()` — cơ chế human-in-the-loop CÓ SẴN của
LangGraph — ngay trong thân hàm tool: gọi `interrupt(payload)` tạm dừng graph tại đây,
LangGraph tự checkpoint + trả lại đúng giá trị này khi resume qua
`Command(resume=answer)` (`app/agent/graph.py::resume_turn`). Không cần tự dựng khái
niệm "tool chờ"/node chờ riêng như bản trước — `ToolNode` (dùng bên trong
`create_react_agent`, `app/agent/graph.py`) coi tool này như mọi tool khác, chỉ khác ở
chỗ nó không `return` ngay lần đầu.
"""

from langchain.tools import tool
from langgraph.types import interrupt


@tool
def ask_user(question: str, options: list[str] | None = None) -> str:
    """Hỏi lại người dùng khi thiếu thông tin quan trọng để trả lời câu hỏi hiện tại.

    Args:
        question: Câu hỏi ngắn gọn để hỏi lại người dùng.
        options: Danh sách lựa chọn gợi ý (để trống nếu muốn người dùng tự nhập).

    Turn sẽ tạm dừng, chờ người dùng chọn/nhập rồi mới tiếp tục — không đoán khi thiếu
    thông tin quan trọng (tình trạng da, tiền sử, thuốc đang dùng...).
    """
    answer = interrupt({"question": question, "options": options or []})
    return str(answer)

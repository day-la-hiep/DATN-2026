
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

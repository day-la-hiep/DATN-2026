"""Tool `make_plan` — buộc model "nói ra" kế hoạch TRƯỚC khi hành động, quan sát được
qua stream (khác text thường).

Vấn đề: model hiện dùng (`AGENT_MODEL`, `app/core/config.py`) là Gemma qua OpenRouter,
đã verify thực nghiệm trả `content=''` TUYỆT ĐỐI mỗi khi quyết định gọi tool (giới hạn
của provider/model, không sửa được bằng system prompt — xem thảo luận trong lịch sử hội
thoại). Middleware `emit_reasoning_step`/`emit_tool_result` (`app/agent/graph.py`) chỉ
phát được những gì có trong response: `tool_calls` luôn có, `content` thì không — nên
cách DUY NHẤT để "kế hoạch" hiển thị ra ngoài là biến nó thành 1 lệnh gọi tool thật, với
tham số CHÍNH LÀ nội dung kế hoạch. Tool này không tra cứu gì, chỉ echo lại kế hoạch làm
xác nhận — mọi giá trị quan sát nằm ở `tool_calls.args` (đã stream qua
`message.thinking`) và `content` trả về (stream qua `message.tool_result`).
"""

from langchain_core.tools import tool


@tool
def make_plan(entities: list[str], planned_tools: list[str], reasoning: str) -> str:
    """BẮT BUỘC gọi tool này ĐẦU TIÊN cho mỗi lượt có nội dung y khoa (mục 3
    SYSTEM_PROMPT), TRƯỚC bất kỳ tool nào khác — nêu ngắn gọn kế hoạch sẽ làm gì và tại
    sao. Không tra cứu dữ liệu gì, chỉ ghi nhận kế hoạch để người dùng thấy được bước suy
    luận trước khi agent hành động.

    Args:
        entities: Tên các thực thể (bệnh/triệu chứng/thuốc) dự định kiểm tra ở bước tiếp
            theo, lấy từ câu hỏi/mô tả của người dùng.
        planned_tools: Tên các tool dự định gọi tiếp theo, theo đúng thứ tự dự kiến (vd
            ["ground_medical_entities", "search_disease_guidelines"]).
        reasoning: 1-2 câu ngắn gọn giải thích vì sao chọn hướng tra cứu này (vd ứng viên
            nào đang nghi ngờ, còn thiếu thông tin gì).
    """
    lines = [f"Kế hoạch: {reasoning}"]
    if entities:
        lines.append(f"Thực thể sẽ kiểm tra: {', '.join(entities)}")
    if planned_tools:
        lines.append(f"Tool dự định gọi: {', '.join(planned_tools)}")
    return "\n".join(lines)

"""
tools.py
========
Định nghĩa Tool Search để LLM (OpenAI-compatible) có thể gọi
hàm tìm kiếm trong FAISS index.

Cách dùng trong DermChatEngine:
    from .tools import SEARCH_TOOLS, execute_tool

    # Gửi cho LLM
    response = client.responses.create(
        model=...,
        tools=SEARCH_TOOLS,
        input=user_message,
    )

    # Nếu LLM gọi tool
    if response.output[0].type == "function_call":
        result = execute_tool(
            tool_name=response.output[0].name,
            args=json.loads(response.output[0].arguments),
            retriever=semantic_retriever,
        )
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .semantic import SemanticRetriever


# ---------------------------------------------------------------------------
# Tool Schema (OpenAI Responses API / Chat Completions API format)
# ---------------------------------------------------------------------------

SEARCH_TOOLS: list[dict] = [
    {
        "type": "function",
        "name": "search_disease_guidelines",
        "description": (
            "Tìm kiếm thông tin bệnh da liễu từ hướng dẫn lâm sàng (BYT 75/2015, WHO, MedlinePlus). "
            "Gọi hàm này khi người dùng: mô tả triệu chứng, hỏi về một bệnh cụ thể, "
            "hỏi cách phân biệt hai bệnh, hỏi điều trị/chăm sóc, hoặc hỏi yếu tố nguy cơ."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Câu hỏi hoặc mô tả triệu chứng của người dùng. "
                        "Giữ nguyên ngôn ngữ và ngữ cảnh gốc."
                    ),
                },
                "chunk_type": {
                    "type": "string",
                    "enum": ["overview", "symptoms", "differential", "advice", "risk", "all"],
                    "description": (
                        "Loại thông tin cần tìm:\n"
                        "- overview: định nghĩa, mô tả chung về bệnh\n"
                        "- symptoms: triệu chứng, dấu hiệu lâm sàng, vị trí tổn thương\n"
                        "- differential: phân biệt chẩn đoán giữa các bệnh\n"
                        "- advice: lời khuyên chăm sóc, điều trị tại nhà\n"
                        "- risk: yếu tố nguy cơ, dấu hiệu cảnh báo nguy hiểm\n"
                        "- all: tìm trong tất cả loại chunk (mặc định)"
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "Số kết quả trả về (1–10). Mặc định: 3.",
                },
            },
            "required": ["query"],
        },
    }
]

# Định dạng cũ hơn (Chat Completions format), dùng nếu cần tương thích
SEARCH_TOOLS_CHAT_FORMAT: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["parameters"],
        },
    }
    for tool in SEARCH_TOOLS
]


# ---------------------------------------------------------------------------
# Hàm format kết quả để gửi lại cho LLM
# ---------------------------------------------------------------------------

def format_search_results(results: list[dict]) -> str:
    """
    Chuyển list chunk kết quả thành văn bản ngắn gọn để LLM đọc.
    Mỗi kết quả hiển thị: tên bệnh, loại chunk, score, nội dung text.
    """
    if not results:
        return "Không tìm thấy thông tin phù hợp trong cơ sở dữ liệu."

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        disease_name = r.get("disease_name", r.get("disease", {}).get("name", "?"))
        chunk_type = r.get("chunk_type", "?")
        score = r.get("score", 0.0)
        text = r.get("text", "")
        source_label = r.get("source_label", "")
        source_page = r.get("source_page")

        source_info = source_label
        if source_page:
            source_info += f" tr.{source_page}"

        lines.append(
            f"[{i}] {disease_name} ({chunk_type}) — độ liên quan: {score:.2f}\n"
            f"    {text}\n"
            f"    Nguồn: {source_info}"
        )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Executor: thực thi tool call từ LLM
# ---------------------------------------------------------------------------

def execute_tool(
    tool_name: str,
    args: dict,
    retriever: "SemanticRetriever",
) -> str:
    """
    Thực thi 1 tool call do LLM yêu cầu và trả về chuỗi kết quả.

    Args:
        tool_name: tên tool LLM muốn gọi
        args: dict arguments từ LLM (đã parse từ JSON)
        retriever: SemanticRetriever instance đang chạy

    Returns:
        Chuỗi văn bản kết quả để trả lại cho LLM tiếp tục sinh response
    """
    if tool_name != "search_disease_guidelines":
        return f"[ERROR] Tool không được hỗ trợ: {tool_name}"

    if not retriever.available:
        return f"[UNAVAILABLE] Semantic index chưa sẵn sàng: {retriever.reason}"

    query: str = args.get("query", "").strip()
    if not query:
        return "[ERROR] Thiếu tham số 'query'."

    chunk_type: str = args.get("chunk_type", "all")
    top_k: int = min(max(int(args.get("top_k", 3)), 1), 10)

    # Gọi search (có filter theo chunk_type nếu không phải "all")
    raw_results = retriever.search(query, limit=top_k, chunk_type=chunk_type)

    # Chuyển Match objects sang dict để format
    result_dicts: list[dict] = []
    for match in raw_results:
        chunk_data = match.disease  # SemanticRetriever lưu chunk metadata trong disease field
        result_dicts.append(
            {
                "disease_name": chunk_data.get("disease_name", chunk_data.get("name", "?")),
                "chunk_type": chunk_data.get("chunk_type", "unknown"),
                "score": match.score,
                "text": chunk_data.get("text", ""),
                "source_label": chunk_data.get("source_label", ""),
                "source_page": chunk_data.get("source_page"),
            }
        )

    return format_search_results(result_dicts)


# ---------------------------------------------------------------------------
# Helper: parse tool call từ OpenAI Responses API output
# ---------------------------------------------------------------------------

def parse_tool_call(output_item) -> tuple[str, dict] | None:
    """
    Parse 1 item trong response.output của OpenAI Responses API.
    Trả về (tool_name, args_dict) hoặc None nếu không phải tool call.
    """
    try:
        if getattr(output_item, "type", None) == "function_call":
            name = output_item.name
            args = json.loads(output_item.arguments)
            return name, args
    except Exception:
        pass
    return None

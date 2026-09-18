"""Medical RAG: tạo ngữ cảnh có nguồn và kiểm tra đầu ra trước khi trả người dùng."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .semantic import SemanticRetriever

SYSTEM_INSTRUCTIONS = """Bạn là trợ lý thông tin da liễu bằng tiếng Việt.
Chỉ dùng THÔNG TIN THAM CHIẾU được cung cấp; không suy diễn thêm.
Không chẩn đoán chắc chắn, không kê đơn, không nêu liều thuốc.
Nói rõ đây chỉ là thông tin tham khảo, nêu câu hỏi làm rõ và khuyến nghị khám khi phù hợp.
Không được thay đổi hoặc bỏ qua cảnh báo an toàn. Trả lời ngắn, dễ hiểu.
"""

BLOCKED_CLAIMS = ("chắc chắn bạn bị", "tôi chẩn đoán", "hãy dùng liều", "uống ngay")


def evidence_context(result: dict) -> str:
    """Đưa cho LLM đúng phần evidence từ retrieval, không đưa toàn bộ knowledge base."""
    condition_by_id = {item["id"]: item for item in result.get("possible_conditions", [])}
    lines: list[str] = []
    for evidence in result.get("evidence", []):
        condition = condition_by_id.get(evidence["condition_id"])
        source = evidence.get("source", {})
        if not condition:
            continue
        lines.extend(
            [
                f"- Điều kiện tham khảo: {condition['name']}",
                f"  Tóm tắt: {condition['summary']}",
                f"  Nguồn: {source.get('title', 'Chưa có nguồn')} — {source.get('url', '')}",
            ]
        )
    return "\n".join(lines) or "Không có evidence phù hợp."


def output_is_safe(text: str) -> bool:
    folded = text.casefold()
    return bool(text.strip()) and len(text) <= 4_000 and not any(
        phrase in folded for phrase in BLOCKED_CLAIMS
    )


@dataclass
class GenerationResult:
    text: str | None
    mode: str
    note: str | None = None


class OpenAIGroundedResponder:
    """Tùy chọn. Không gọi mạng nếu người vận hành chưa cấu hình API key."""

    def __init__(self, semantic_retriever: "SemanticRetriever | None" = None) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._retriever = semantic_retriever

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, message: str, result: dict) -> GenerationResult:
        if not self.configured:
            return GenerationResult(None, "deterministic", "OPENAI_API_KEY chưa được cấu hình.")
        try:
            from openai import OpenAI

            from .tools import SEARCH_TOOLS_CHAT_FORMAT, execute_tool

            client = OpenAI(api_key=self.api_key)

            # Xây dựng messages ban đầu
            messages: list[dict] = [
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": (
                        f"CÂU HỎI NGƯỜI DÙNG:\n{message}\n\n"
                        f"THÔNG TIN THAM CHIẾU SẴN CÓ:\n{evidence_context(result)}\n\n"
                        "Hãy trả lời người dùng. Nếu cần tra cứu thêm thông tin chi tiết "
                        "về triệu chứng, phân biệt chẩn đoán hoặc lời khuyên, hãy dùng tool."
                    ),
                },
            ]

            # Chỉ gửi tool khi semantic retriever sẵn sàng
            tools = (
                SEARCH_TOOLS_CHAT_FORMAT
                if self._retriever and self._retriever.available
                else None
            )

            # Tool Search loop: tối đa 3 vòng để tránh vòng lặp vô tận
            tool_calls_made: list[str] = []
            for _round in range(3):
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    tools=tools,
                    tool_choice="auto" if tools else None,
                )
                choice = response.choices[0]

                # Nếu LLM trả response text thẳng → kết thúc
                if choice.finish_reason == "stop" or not choice.message.tool_calls:
                    text = (choice.message.content or "").strip()
                    if not output_is_safe(text):
                        return GenerationResult(
                            None, "deterministic", "Đầu ra LLM không qua validation."
                        )
                    mode = "openai_tool_rag" if tool_calls_made else "openai_rag"
                    return GenerationResult(text, mode)

                # LLM muốn gọi tool — thêm assistant message vào history
                messages.append(
                    {
                        "role": "assistant",
                        "content": choice.message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in choice.message.tool_calls
                        ],
                    }
                )

                # Thực thi từng tool call và trả kết quả về LLM
                for tc in choice.message.tool_calls:
                    tool_args = json.loads(tc.function.arguments)
                    tool_calls_made.append(
                        f"{tc.function.name}(chunk_type={tool_args.get('chunk_type','all')})"
                    )
                    if self._retriever:
                        tool_result = execute_tool(tc.function.name, tool_args, self._retriever)
                    else:
                        tool_result = "[UNAVAILABLE] Semantic retriever chưa sẵn sàng."

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_result,
                        }
                    )

            # Quá 3 vòng mà chưa có text → fallback deterministic
            return GenerationResult(
                None, "deterministic", "LLM không hoàn thành sau 3 vòng tool call."
            )

        except Exception as error:
            # Không lộ lỗi nội bộ hoặc credential cho người dùng cuối.
            return GenerationResult(
                None, "deterministic", f"LLM không khả dụng: {type(error).__name__}"
            )

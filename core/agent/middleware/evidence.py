"""Kiểm soát bằng chứng của lượt tư vấn — chặn hai lỗi mà prompt một mình không giữ được:

  1. Dữ kiện nguồn "user" mà người dùng chưa từng nói (model tự bịa chi tiết rồi dùng nó xếp hạng bệnh).
  2. Nêu giả thuyết / xếp hạng bệnh khi mọi lần tra cứu (sách, web) đều không trả về bằng chứng.

"Có bằng chứng" nghĩa là có đoạn sách (`hybrid_retrieval` / `semantic_search` / `keyword_search`, kết quả `source="book"`) hoặc trang web uy tín. Quan hệ đồ thị (`kg`) chỉ là
gợi ý và kết quả phân loại ảnh chỉ là giả thuyết (SYSTEM_PROMPT mục 1, 5) nên không tính.

Ba lớp, từ sớm đến muộn: (a) chèn quy tắc vào system prompt ngay trước lần gọi model khi đã tra cứu mà không có bằng chứng; (b) từ
chối `record_reasoning` có dữ kiện "user" không truy được về lời người dùng hoặc có giả thuyết khi không có bằng chứng; (c) lưới an
toàn: câu trả lời cuối vẫn nhắc tên giả thuyết thì bắt viết lại (bản nháp có thể đã stream ra — giới hạn đã biết, giống
`enforce_initial_reasoning`)."""
import json
import re
from typing import Any, Awaitable, Callable, Literal

from langchain.agents import AgentState
from langchain.agents.middleware import (
    ModelRequest,
    ModelResponse,
    Runtime,
    ToolCallRequest,
    after_model,
    wrap_model_call,
    wrap_tool_call,
)
from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

from agent.state.context import AgentContext
from agent.tools.reasoning import FEEDBACK_PREFIX, INVALID_PREFIX, TOOL_NAME as REASONING_TOOL, turn_messages

EVIDENCE_FEEDBACK_PREFIX = "[Hệ thống kiểm soát bằng chứng — không phải lời người dùng]"
MAX_EVIDENCE_RETRIES = 2

# Tool tra cứu có thể cho bằng chứng; `search_trusted_web` / `fetch_trusted_page` thành công luôn mở đầu bằng khối đánh dấu này.
# `knowledge_graph_search` tính là đã tra cứu nhưng không bao giờ cho bằng chứng (kết quả `source="kg"` chỉ là gợi ý).
_RETRIEVAL_TOOLS = {"hybrid_retrieval", "semantic_search", "keyword_search", "knowledge_graph_search", "search_trusted_web", "fetch_trusted_page"}
_JSON_RESULT_TOOLS = {"hybrid_retrieval", "semantic_search", "keyword_search", "knowledge_graph_search"}
_WEB_MARKER = "[DỮ LIỆU NGOÀI TỪ WEB"

# Dữ kiện "user" phải trùng ít nhất chừng này từ khoá với lời người dùng (kể cả câu trả lời `ask_user`) — đủ rộng cho cách diễn
# đạt lại, đủ chặt để bắt chi tiết chưa từng được nói.
_MIN_OVERLAP = 0.5
_WORD = re.compile(r"\w+", re.UNICODE)
_STOP = {
    "có", "không", "và", "của", "là", "bị", "ở", "cũng", "đang", "với", "một", "các", "những", "này", "khi", "để", "đã", "rất", "thì",
    "mà", "cho", "từ", "tại", "ra", "vào", "nhưng", "hoặc", "nên", "như", "được", "tôi", "em", "anh", "chị", "bác", "sĩ", "ơi",
    # từ "kể lại" (model hay viết "người dùng trả lời ... khi được hỏi ...") — không mang thông tin y khoa nên không tính
    "người", "dùng", "trả", "lời", "hỏi", "nói", "biết", "về", "mô", "tả",
}

Status = Literal["untried", "none", "found"]


def _text(message: AnyMessage) -> str:
    return message.content if isinstance(message.content, str) else str(message.content)


def _has_evidence(tool: str, content: str) -> bool:
    if tool in _JSON_RESULT_TOOLS:
        try:
            results = json.loads(content).get("results") or []
        except (ValueError, AttributeError):
            return False
        return any(isinstance(r, dict) and r.get("source") == "book" for r in results)
    return content.startswith(_WEB_MARKER)


def evidence_status(turn: list[AnyMessage]) -> Status:
    """`untried`: chưa gọi tool tra cứu nào trong lượt; `none`: đã gọi nhưng không cái nào cho bằng chứng; `found`: có bằng chứng."""
    tried = False
    for m in turn:
        if isinstance(m, ToolMessage) and m.name in _RETRIEVAL_TOOLS:
            tried = True
            if _has_evidence(m.name or "", _text(m)):
                return "found"
    return "none" if tried else "untried"


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 2 and w not in _STOP}


def user_text(messages: list[AnyMessage]) -> str:
    """Mọi điều người dùng đã nói trong hội thoại: tin của họ ở các lượt (bỏ tin nội bộ do middleware chèn) và câu trả lời `ask_user`."""
    parts = [
        _text(m)
        for m in messages
        if (isinstance(m, HumanMessage) and not _text(m).startswith(("[Hệ thống", FEEDBACK_PREFIX)))
        or (isinstance(m, ToolMessage) and m.name == "ask_user")
    ]
    return "\n".join(parts)


def unsupported_user_facts(args: dict[str, Any], said: str) -> list[str]:
    """Dữ kiện nguồn "user" không truy được về lời người dùng (đối chiếu theo từ khoá)."""
    said_tokens = _tokens(said)
    bad: list[str] = []
    for obs in args.get("observations") or []:
        if not isinstance(obs, dict) or str(obs.get("source", "")).strip().lower() != "user":
            continue
        fact = str(obs.get("fact", ""))
        tokens = _tokens(fact)
        if tokens and len(tokens & said_tokens) / len(tokens) < _MIN_OVERLAP:
            bad.append(fact)
    return bad


def _hypothesis_terms(turn: list[AnyMessage]) -> set[str]:
    """Tên các giả thuyết model đã nêu qua `record_reasoning` trong lượt (cả tên tiếng Anh trong ngoặc / sau dấu "/")."""
    terms: set[str] = set()
    for m in turn:
        if not isinstance(m, AIMessage):
            continue
        for call in m.tool_calls:
            if call["name"] != REASONING_TOOL:
                continue
            for h in call["args"].get("hypotheses") or []:
                for part in re.split(r"[()/,]", str(h.get("disease", "") if isinstance(h, dict) else "")):
                    if len(part.strip()) >= 3:
                        terms.add(part.strip().lower())
    return terms


_NO_EVIDENCE_RULES = (
    "\n\n[KIỂM SOÁT BẰNG CHỨNG — bắt buộc] Các lần tra cứu trong lượt này KHÔNG trả về bằng chứng (sách / web). Từ giờ tới hết lượt: "
    "KHÔNG nêu tên bệnh nào như một khả năng, giả thuyết hay chẩn đoán, KHÔNG xếp hạng, KHÔNG nêu độ tin cậy, KHÔNG đưa lời khuyên "
    "điều trị hay chăm sóc cụ thể, KHÔNG ghi dữ kiện nguồn \"user\" nào ngoài đúng lời người dùng đã nói. Khi gọi `record_reasoning` "
    "(stage after_evidence / final) để `hypotheses` là danh sách rỗng. Chỉ được: (1) nói rõ mình chưa tra cứu được nguồn nào để đối "
    "chiếu nên chưa thể nhận định về bệnh; (2) nhắc lại những gì người dùng đã mô tả; (3) hỏi thêm thông tin còn thiếu bằng "
    "`ask_user` HOẶC khuyên khám da liễu kèm các dấu hiệu cần đi khám ngay; (4) nhắc đây là thông tin tham khảo."
)


@wrap_model_call
async def evidence_rules(
    request: ModelRequest[AgentContext],
    handler: Callable[[ModelRequest[AgentContext]], Awaitable[ModelResponse]],
) -> ModelResponse:
    """(a) Đã tra cứu mà không có bằng chứng -> thêm quy tắc cứng vào system prompt cho các lần gọi model còn lại của lượt."""
    if evidence_status(turn_messages(request.state["messages"])) == "none":
        base = request.system_message.content if request.system_message else ""
        request = request.override(system_message=SystemMessage(content=f"{base}{_NO_EVIDENCE_RULES}"))
    return await handler(request)


@wrap_tool_call
async def evidence_reasoning_check(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
) -> ToolMessage | Command[Any]:
    """(b) Từ chối `record_reasoning` bịa dữ kiện "user", hoặc nêu giả thuyết khi không có bằng chứng."""
    call = request.tool_call
    if call["name"] != REASONING_TOOL:
        return await handler(request)

    args = call.get("args") or {}
    messages: list[AnyMessage] = request.state["messages"]
    problems: list[str] = []

    invented = unsupported_user_facts(args, user_text(messages))
    if invented:
        problems.append(
            "Dữ kiện nguồn \"user\" mà người dùng CHƯA nói: " + "; ".join(f'"{f}"' for f in invented) + ". Chỉ ghi dữ kiện đúng theo "
            'lời người dùng; điều chưa biết thì để ở "missing" hoặc hỏi họ — không được tự điền.'
        )
    if (
        args.get("stage") in ("after_evidence", "final")
        and args.get("hypotheses")
        and evidence_status(turn_messages(messages)) == "none"
    ):
        problems.append(
            "Các lần tra cứu chưa trả về bằng chứng (sách / web) nên chưa có giả thuyết nào đủ căn cứ: gọi lại với "
            "`hypotheses` là danh sách rỗng."
        )
    if problems:
        return ToolMessage(
            content=f"{INVALID_PREFIX} " + " | ".join(problems),
            name=REASONING_TOOL,
            tool_call_id=call.get("id", ""),
            status="error",
        )
    return await handler(request)


@after_model(can_jump_to=["model"])
async def evidence_answer_check(state: AgentState[Any], runtime: Runtime[AgentContext]) -> dict[str, Any] | None:
    """(c) Lưới an toàn: câu trả lời cuối khi không có bằng chứng mà vẫn nhắc tên giả thuyết đã nêu -> bắt viết lại."""
    messages = state["messages"]
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or last.tool_calls or not last.text.strip():
        return None
    turn = turn_messages(messages[:-1])
    if evidence_status(turn) != "none":
        return None
    if sum(1 for m in turn if isinstance(m, HumanMessage) and _text(m).startswith(EVIDENCE_FEEDBACK_PREFIX)) >= MAX_EVIDENCE_RETRIES:
        return None

    said = user_text(messages[:-1]).lower()
    answer = last.text.lower()
    mentioned = sorted(t for t in _hypothesis_terms(turn) if t in answer and t not in said)
    if not mentioned:
        return None
    return {
        "messages": [
            HumanMessage(
                content=(
                    f"{EVIDENCE_FEEDBACK_PREFIX} Câu trả lời vừa rồi nêu tên bệnh ({', '.join(mentioned)}) như một khả năng trong khi "
                    "các lần tra cứu không trả về bằng chứng nào. Hãy viết lại theo quy tắc kiểm soát bằng chứng: không nêu tên "
                    "bệnh / xếp hạng / độ tin cậy; nói rõ chưa tra cứu được nguồn để đối chiếu, nhắc lại điều người dùng đã mô tả, "
                    "rồi hỏi thêm hoặc khuyên khám da liễu."
                )
            )
        ],
        "jump_to": "model",
    }

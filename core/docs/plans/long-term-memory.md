# Long-term memory cho Agent — Qdrant + distill bằng LLM

## Context

Hiện tại Agent **không có bất kỳ cơ chế nhớ nào** ngoài phạm vi 1 turn: `worker.py::_initial_state()`
build `messages` chỉ từ **đúng 1 `HumanMessage`** (nội dung tin nhắn hiện tại) — kể cả trong
CÙNG 1 hội thoại, turn mới hoàn toàn không thấy lịch sử turn trước (LangGraph checkpointer dùng
`thread_id = message_id` của TỪNG turn, không phải `conversation_id`, nên state cũng không tự
nối giữa các turn). Yêu cầu: thêm long-term memory, trong đó memory được **tóm tắt (distill)
từ tool call/reasoning/kết quả mỗi turn** (không lưu raw), lưu vào **Qdrant** (vector DB, không
phải bảng Postgres), và truy xuất bằng **semantic search** để làm context cho LLM ở turn mới —
áp dụng thống nhất cho cả 2 phạm vi (trong cùng hội thoại VÀ xuyên các hội thoại khác nhau của
cùng 1 user): dùng chung 1 cơ chế duy nhất — semantic search theo `user_id`, không phân biệt
nguồn gốc hội thoại, nên tự nhiên phủ cả 2 trường hợp mà không cần thêm logic riêng.

Đã xác nhận với user: (1) phạm vi = cả trong-hội-thoại + xuyên-hội-thoại, (2) nội dung memory =
tóm tắt qua 1 lần gọi LLM (không lưu raw), (3) **lưu trữ = Qdrant** (đổi hướng so với đề xuất
Postgres ban đầu — quyết định cuối), (4) truy xuất = semantic search bằng embedding (đi cùng
với quyết định #3, thay cho "theo thời gian gần nhất" đã đề xuất trước đó).

Project hiện **chưa có** Qdrant/embedding nào (`qdrant-client` chưa cài, không có service
`qdrant` trong `docker-compose.yml` của repo này — container `qdrant` thấy trên máy dev thuộc
1 project khác, không dùng lại). `langchain-google-genai` (đã cài, dùng cho `AGENT_MODEL`) có
sẵn `GoogleGenerativeAIEmbeddings` — dùng luôn, không cần thêm provider mới.

**Nguyên tắc ranh giới dữ liệu**: Qdrant là kho dữ liệu HOÀN TOÀN RIÊNG, không phải Postgres —
nguyên tắc "Core là writer duy nhất của bảng `messages`" (từ việc implement `agent_response_queue`
trước đó) chỉ áp dụng cho Postgres, KHÔNG áp dụng ở đây. Agent Worker đọc/ghi Qdrant trực tiếp,
không qua queue/Core.

## Thiết kế

### 1. Hạ tầng — `docker-compose.yml` (gốc repo)

Thêm service `qdrant` (theo đúng pattern `postgres`/`redis`/`rabbitmq` đã có — `container_name`,
`ports` từ biến env có default, named volume, cùng network `derma-net`):

```yaml
  qdrant:
    image: qdrant/qdrant:latest
    container_name: derma-qdrant
    restart: unless-stopped
    ports:
      - "${QDRANT_PORT:-6333}:6333"      # REST
      - "${QDRANT_GRPC_PORT:-6334}:6334" # gRPC
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - derma-net
```
Thêm `qdrant_data:` vào `volumes:`.

### 2. Dependency + config

- `core/pyproject.toml`: thêm `"qdrant-client>=1.7"`.
- `core/app/core/config.py` (`Settings`): thêm
  ```python
  QDRANT_URL: str = "http://localhost:6333"
  QDRANT_COLLECTION: str = "agent_memories"
  ```
- `core/.env`/`.env.example`: thêm 2 biến trên (giá trị default đã đủ chạy dev, giống pattern
  các biến khác trong file).

### 3. Client wrapper — `core/app/infra/qdrant_client.py` (mới)

Cùng phong cách `redis_client.py`/`rabbitmq_client.py` (client dùng chung + hàm module-level,
không phải class service):

```python
"""Qdrant client dùng chung — lưu long-term memory (vector + payload) của Agent."""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchValue, PointStruct, ScoredPoint, VectorParams,
)

from app.core.config import settings

EMBEDDING_DIM = 768  # models/text-embedding-004 (Google)

client = AsyncQdrantClient(url=settings.QDRANT_URL)


async def ensure_collection() -> None:
    """Tạo collection nếu chưa có — gọi 1 lần lúc Agent Worker khởi động (idempotent)."""
    if not await client.collection_exists(settings.QDRANT_COLLECTION):
        await client.create_collection(
            settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


async def upsert_memory(*, point_id: str, vector: list[float], payload: dict[str, object]) -> None:
    await client.upsert(
        settings.QDRANT_COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )


async def search_memories(
    *, user_id: str, vector: list[float], limit: int = 5, score_threshold: float = 0.5
) -> list[ScoredPoint]:
    return await client.search(
        settings.QDRANT_COLLECTION,
        query_vector=vector,
        query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]),
        limit=limit,
        score_threshold=score_threshold,
    )
```

**Lưu ý khi implement**: `qdrant-client` bản mới có thể đã deprecate `.search()` để chuyển sang
`.query_points()` — kiểm tra đúng API theo version cài thực tế (`uv add qdrant-client` xong đọc
changelog/docstring), điều chỉnh nếu cần. Điểm Qdrant yêu cầu `id` là UUID hoặc int không dấu —
dùng `uuid.uuid4()` làm `point_id` (KHÔNG dùng `message_id` dạng `"msg-<uuid4>"` vì có tiền tố,
không phải UUID hợp lệ) — `message_id` vẫn giữ trong `payload` để truy vết.

### 4. Business logic — `core/app/agent/memory.py` (mới)

```python
"""Long-term memory: sau mỗi turn hoàn tất, tóm tắt (distill) qua 1 lần gọi LLM rồi
lưu vector vào Qdrant; đầu mỗi turn mới, semantic search theo `user_id` để lấy
memory liên quan làm context. Dùng CHUNG 1 cơ chế cho cả trong-hội-thoại lẫn
xuyên-hội-thoại — không phân biệt nguồn gốc, chỉ lọc theo `user_id` + độ liên quan.
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

_embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")


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
    *, user_id: str, conversation_id: str, message_id: str,
    user_content: str, reasoning: list[ReasoningResult], answer: str,
) -> None:
    """Gọi SAU khi turn kết thúc thành công (status="done"). Không raise — lỗi chỉ
    log, không được làm hỏng turn đã xong (xem `worker.py::_drive_graph`)."""
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

        vector = await _embeddings.aembed_query(summary)
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
    `user_id` — trả None nếu không có gì liên quan hoặc Qdrant lỗi (KHÔNG chặn turn)."""
    if not query_text.strip():
        return None
    try:
        vector = await _embeddings.aembed_query(query_text)
        hits = await qdrant_client.search_memories(user_id=user_id, vector=vector, limit=limit)
    except Exception as exc:  # noqa: BLE001
        print(f"[Memory] retrieve thất bại: {exc}")
        return None

    if not hits:
        return None
    lines = [f"- {hit.payload['summary']}" for hit in hits]
    return (
        "[Thông tin đã biết về người dùng này từ các lần tư vấn trước — tham khảo "
        "nếu liên quan, không nhất thiết phải nhắc lại]\n" + "\n".join(lines)
    )
```

Dùng `response.text` (property chuẩn hoá của LangChain — KHÔNG `str(response.content)`) để nhất
quán với fix đã áp dụng ở `_run_llm()` (`app/agent/graph.py`) cho model trả `content` dạng list
content-block.

### 5. `core/app/agent/worker.py` — nối vào luồng turn

- **`_initial_state()` → async**, thêm memory context vào đầu `messages`:
  ```python
  async def _initial_state(req: TurnRequest) -> TurnState:
      memory_context = await _load_memory_context(req.conversation_id, req.content or "")
      messages: list[AnyMessage] = []
      if memory_context:
          messages.append(SystemMessage(content=memory_context))
      messages.append(HumanMessage(content=req.content or ""))
      return {
          "conversation_id": req.conversation_id,
          "message_id": req.message_id,
          "messages": messages,
          "steps": [], "current_step": [], "step_count": 0, "just_closed_step": False,
          "outcome": None, "final_answer": None, "pending_tool": None, "last_steer_batch": [],
      }


  async def _load_memory_context(conversation_id: str, query_text: str) -> str | None:
      async with AsyncSessionLocal() as db:
          conversation = await ConversationRepository(db).get(conversation_id)
      if conversation is None:
          return None
      return await memory.retrieve_context(user_id=conversation.user_id, query_text=query_text)
  ```
  Cần import lại `AsyncSessionLocal`, `ConversationRepository` vào `worker.py` (đã bỏ ở lần
  refactor `agent_response_queue` trước — nhưng đó là bỏ WRITE, còn READ vẫn luôn được phép,
  đúng tiền lệ `pre_step`'s `list_pending_steers`). Thêm `from app.agent import memory` và
  import `SystemMessage` (đã có `HumanMessage`, thêm `SystemMessage` vào cùng dòng import
  `langchain_core.messages`).
- **`_handle_turn()`**: đổi `_drive_graph(req, _initial_state(req), ...)` →
  `_drive_graph(req, await _initial_state(req), ...)` (giờ là coroutine).
- **`_handle_resume()`**: KHÔNG đổi — resume dùng `Command(resume=...)`, không tạo lại initial
  state, memory chỉ nạp 1 lần lúc turn thật sự bắt đầu.
- **Sau khi turn hoàn tất thành công** (nhánh `status="done"` trong `_drive_graph`, sau lời gọi
  `_persist_assistant(...)` hiện có), gọi distill:
  ```python
  async with AsyncSessionLocal() as db:
      conversation = await ConversationRepository(db).get(req.conversation_id)
  if conversation is not None:
      user_content = next(
          (m.content for m in last_state["messages"] if isinstance(m, HumanMessage)), ""
      )
      await memory.distill_and_store(
          user_id=conversation.user_id,
          conversation_id=req.conversation_id,
          message_id=req.message_id,
          user_content=str(user_content),
          reasoning=reasoning,
          answer=answer,
      )
  ```
  **Lưu ý quan trọng**: dùng `user_content` lấy từ `HumanMessage` ĐẦU TIÊN trong
  `last_state["messages"]`, KHÔNG dùng `req.content` trực tiếp — vì khi turn được resume
  (`_handle_resume`), `req` là request loại `"resume"` có `content=None` (nội dung gốc nằm ở
  `TurnRequest` của lần request ĐẦU, không phải request resume hiện tại).
  - KHÔNG distill nhánh `interrupted` (turn tạm dừng chờ `ask_user`) — chỉ distill khi turn
    thật sự xong, tránh lưu memory từ 1 turn dở dang.
- **`main()`**: gọi `await qdrant_client.ensure_collection()` trước khi bắt đầu consume
  (tương tự cách `rabbitmq_client.connect()` được gọi trước `consume`).

### 6. Tài liệu

- File mới `core/app/kien-truc-memory.md`: mô tả cơ chế (distill → Qdrant → semantic search),
  tham chiếu `kien-truc-agent.md`. Nêu rõ: memory là tóm tắt (lossy), KHÔNG replay nguyên văn
  hội thoại cũ; 1 cơ chế duy nhất phủ cả 2 phạm vi trong/xuyên hội thoại qua `user_id`.
- `docs/kien-truc-he-thong.md`: thêm Qdrant vào bảng biến môi trường liên service + bảng
  "hiện tại vs định hướng".

## Files thay đổi (tóm tắt)

| File | Thay đổi |
|---|---|
| `docker-compose.yml` | Thêm service `qdrant` + volume |
| `core/pyproject.toml` | Thêm dependency `qdrant-client` |
| `core/app/core/config.py` | Thêm `QDRANT_URL`, `QDRANT_COLLECTION` |
| `core/.env` / `.env.example` | Thêm 2 biến trên |
| `core/app/infra/qdrant_client.py` (mới) | Client wrapper: `ensure_collection`/`upsert_memory`/`search_memories` |
| `core/app/agent/memory.py` (mới) | `distill_and_store()`, `retrieve_context()`, transcript builder |
| `core/app/agent/worker.py` | `_initial_state()` async + nạp memory context; distill sau khi turn `status="done"`; `main()` gọi `ensure_collection()` |
| `core/app/kien-truc-memory.md` (mới) | Tài liệu cơ chế |
| `docs/kien-truc-he-thong.md` | Cập nhật bảng biến môi trường + trạng thái |

## Verify end-to-end

1. `docker compose up -d qdrant` (hoặc `docker compose up -d` full) — kiểm tra `derma-qdrant`
   healthy, `curl http://localhost:6333/collections` trả `{}`  (chưa có collection).
2. `uv sync` (core/) để cài `qdrant-client`.
3. Chạy `cd core && python main.py` + `cd core && python -u -m app.agent.worker` — log Worker
   không lỗi lúc `ensure_collection()`; `curl http://localhost:6333/collections` giờ thấy
   `agent_memories`.
4. Tạo conversation, gửi tin nhắn có 1 fact đáng nhớ (vd "Tôi dị ứng penicillin, da tôi dầu").
   Chờ turn xong (`status="done"`) → kiểm tra Qdrant có point mới:
   `curl -X POST http://localhost:6333/collections/agent_memories/points/scroll -d '{"limit":10,"with_payload":true}' -H "Content-Type: application/json"`
   — thấy `summary` nhắc tới dị ứng penicillin.
5. Tạo conversation MỚI (cùng `userId=user-1`), gửi tin nhắn liên quan (vd "Tôi nên dùng thuốc
   gì cho mụn viêm?") — verify qua log `print` tạm trong `retrieve_context`/quan sát câu trả
   lời của model có tự động tránh/nhắc tới dị ứng penicillin đã ghi nhớ trước đó — xác nhận
   memory xuyên hội thoại hoạt động.
6. Tắt container `derma-qdrant` giữa chừng, gửi 1 tin nhắn khác — xác nhận turn vẫn chạy xong
   bình thường (memory retrieve/store chỉ log lỗi, không chặn), đúng yêu cầu không làm hỏng
   luồng chính khi Qdrant down.

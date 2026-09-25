"""Agent worker — tiến trình riêng, tách khỏi FastAPI process.

Luồng:
  1. consume RabbitMQ `agent_request_queue` (Core đẩy turn mới/Steer/resume, xem
     `agent/dto/schemas.py::TurnRequest`).
  2. mỗi turn xử lý ở `agent/turn.py` (chạy `agent_graph`, forward token lên
     Redis `agent:events:{id}`).
  3. Khi turn xong/tạm dừng, `agent/handler/publisher.py` publish `AgentResponseMessage`
     vào `agent_response_queue` — Worker KHÔNG đụng Postgres để ghi, Core là consumer duy
     nhất làm upsert (`agent/handler/response_consumer.py`).

File này chỉ lo vòng đời tiến trình: nhận message, khoá theo hội thoại, chạy `main`.

Chạy: cd core && python -m agent.worker
"""

import asyncio
import json
from collections import defaultdict

from aio_pika.abc import AbstractIncomingMessage

from agent.dto.schemas import TurnRequest
from agent.turn import handle_resume, handle_turn
from app.core.config import log_startup_infra, settings
from app.core.constants import AGENT_REQUEST_QUEUE
from app.infra.rabbitmq_client import rabbitmq_client

# 1 Lock/conversation_id — `create_agent` KHÔNG hỗ trợ 2 lần `ainvoke()` đồng thời trên
# CÙNG `thread_id` (đụng checkpoint). Turn/Steer mới tới khi turn TRƯỚC của CÙNG hội
# thoại chưa xong sẽ CHỜ tới lượt thay vì chen ngang giữa chừng (đánh đổi có chủ đích —
# đơn giản hơn nhiều so với node `pre_step` tự dựng của bản trước, chấp nhận Steer chỉ
# thực sự được xử lý ngay SAU khi turn hiện tại xong thay vì ngay lập tức).
_conversation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _on_message(message: AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
            req = TurnRequest.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"[Agent Worker] invalid message: {exc}")
            return

        async with _conversation_locks[req.conversation_id]:
            try:
                if req.type == "resume":
                    await handle_resume(req)
                else:
                    await handle_turn(req)
            except Exception as exc:  # noqa: BLE001
                print(f"[Agent Worker] error: {exc}")


async def main() -> None:
    log_startup_infra()
    print(f"[Agent Worker] model: {settings.AGENT_MODEL}")
    await rabbitmq_client.connect()
    print(f"[Agent Worker] listening on '{AGENT_REQUEST_QUEUE}'...")
    await rabbitmq_client.consume(AGENT_REQUEST_QUEUE, _on_message)
    await asyncio.Event().wait()  # chạy tới khi bị dừng (Ctrl+C)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Agent Worker] stopped.")

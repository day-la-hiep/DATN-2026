
import asyncio
import json
import logging
from collections import defaultdict

from aio_pika.abc import AbstractIncomingMessage

from agent.dto.schemas import TurnRequest
from agent.turn import handle_resume, handle_turn
from app.config.log import request_id_var, setup_logging
from app.config.settings import log_startup_infra, settings
from app.config.constants import AGENT_REQUEST_QUEUE
from app.api.deps import close_clients, get_rabbitmq_client

# 1 Lock/conversation_id — `create_agent` KHÔNG hỗ trợ 2 lần `ainvoke()` đồng thời trên
# CÙNG `thread_id` (đụng checkpoint). Core đã chặn tin mới khi turn đang chạy, lock này là
# lớp bảo vệ cuối nếu vẫn có 2 request cùng hội thoại lọt vào queue.
logger = logging.getLogger("worker")
_conversation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _on_message(message: AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
            req = TurnRequest.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("message không hợp lệ: %s", exc)
            return

        request_id_var.set(req.message_id[:8])  # mọi dòng log của turn (kể cả trace LLM/tool) mang cùng mã này
        async with _conversation_locks[req.conversation_id]:
            try:
                logger.info("turn bắt đầu: type=%s conversation=%s", req.type, req.conversation_id)
                if req.type == "resume":
                    await handle_resume(req)
                else:
                    await handle_turn(req)
                logger.info("turn kết thúc")
            except Exception as exc:  # noqa: BLE001
                logger.exception("turn %s lỗi", req.conversation_id)


async def main() -> None:
    setup_logging("worker")
    log_startup_infra()
    logger.info("model: %s", settings.AGENT_MODEL)
    await get_rabbitmq_client().connect()
    logger.info("đang lắng nghe queue '%s'", AGENT_REQUEST_QUEUE)
    await get_rabbitmq_client().consume(AGENT_REQUEST_QUEUE, _on_message)
    try:
        await asyncio.Event().wait()  # chạy tới khi bị dừng (Ctrl+C)
    finally:
        await close_clients()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger("worker").info("đã dừng")

"""Ingest worker — tiến trình riêng chạy các bước pipeline tài liệu (OCR/Docling, embedding rất nặng nên không để chung với Core).

Luồng:
  1. Core (`DocumentIngestPipelineService.start_stage`) ghi stage `running` rồi publish `document_ingest_queue`.
  2. Worker nhận message, chạy `execute` trong thread (code stage là đồng bộ) và tự ghi kết quả vào Postgres/MinIO.
  3. Bấm Dừng: Core đặt cờ key + publish Redis `document:ingest:cancel`; worker set `threading.Event` của lần chạy tương ứng.

Mỗi lần chỉ chạy một bước (Docling chiếm hết CPU/RAM). Khi worker khởi động, queue bị xoá và mọi bước còn `running` chuyển
`failed`, vì không biết chúng còn tiến trình nào chạy — người duyệt bấm chạy lại (OCR có checkpoint nên không mất công).

Chạy: cd core && python -m app.workers.document_ingest_worker
"""

import asyncio
import json
import logging
import threading

from aio_pika.abc import AbstractIncomingMessage

from app.api.deps import (
    close_clients,
    get_document_ingest_pipeline_service,
    get_document_service,
    get_rabbitmq_client,
    get_redis_client,
)
from app.config.constants import (
    DOCUMENT_CANCEL_KEY,
    DOCUMENT_INGEST_CANCEL_CHANNEL,
    DOCUMENT_INGEST_QUEUE,
)
from app.config.log import setup_logging
from app.config.settings import log_startup_infra

logger = logging.getLogger("document_worker")

# (document_id, stage_id) -> cờ dừng của lần chạy đang diễn ra
_cancels: dict[tuple[str, str], threading.Event] = {}
_one_at_a_time = asyncio.Semaphore(1)


async def _on_message(message: AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
            document_id, stage_id = payload["document_id"], payload["stage_id"]
            options = payload.get("options") or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("message không hợp lệ: %s", exc)
            return

        async with _one_at_a_time:
            cancel = threading.Event()
            _cancels[(document_id, stage_id)] = cancel
            try:
                # bấm Dừng khi bước còn nằm trong queue: Pub/Sub đã lỡ nên đọc cờ key
                key = DOCUMENT_CANCEL_KEY.format(document_id=document_id, stage_id=stage_id)
                if await get_redis_client().get_del(key):
                    cancel.set()
                logger.info("chạy bước %s của %s", stage_id, document_id)
                svc = get_document_ingest_pipeline_service()
                # execute đã ghi failed/cancelled + nhật ký vào DB trước khi ném lỗi
                await asyncio.to_thread(svc.execute, document_id, stage_id, options, cancel=cancel)
                logger.info("xong bước %s của %s", stage_id, document_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("bước %s của %s kết thúc không thành công: %s", stage_id, document_id, exc)
            finally:
                _cancels.pop((document_id, stage_id), None)


async def _listen_cancel() -> None:
    async for msg in get_redis_client().subscribe(DOCUMENT_INGEST_CANCEL_CHANNEL):
        try:
            data = json.loads(str(msg["data"]))
            event = _cancels.get((data["document_id"], data["stage_id"]))
        except Exception:  # noqa: BLE001
            continue
        if event is not None:
            event.set()


async def main() -> None:
    setup_logging("document_worker")
    log_startup_infra()
    rabbit = get_rabbitmq_client()
    await rabbit.connect()
    queue = await rabbit.declare_queue(DOCUMENT_INGEST_QUEUE)
    await queue.purge()
    failed = await asyncio.to_thread(get_document_service().fail_orphaned_runs)
    if failed:
        logger.warning("đánh dấu failed %d bước bị bỏ dở từ lần chạy trước", failed)
    cancel_task = asyncio.create_task(_listen_cancel())
    logger.info("đang lắng nghe queue '%s'", DOCUMENT_INGEST_QUEUE)
    await rabbit.consume(DOCUMENT_INGEST_QUEUE, _on_message)
    try:
        await asyncio.Event().wait()
    finally:
        cancel_task.cancel()
        await close_clients()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger("document_worker").info("đã dừng")

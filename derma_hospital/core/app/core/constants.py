"""Tên queue (RabbitMQ) và channel (Redis Pub/Sub) dùng chung toàn app."""

# ----- RabbitMQ queues -----
AGENT_REQUEST_QUEUE = "agent_request_queue"  # Backend -> Agent (yêu cầu 1 turn)
AGENT_RESPONSE_QUEUE = "agent_response_queue"  # Agent -> Backend (kết quả để persist DB)

# ----- Redis Pub/Sub -----
AGENT_EVENTS_CHANNEL = "agent:events:{conversation_id}"  # Agent -> SSE client (stream realtime)
STREAM_DONE_SENTINEL = "[DONE]"  # đánh dấu kết thúc 1 stream SSE

# ----- Redis key (không phải Pub/Sub) -----
# Giá trị = messageId của turn đang chạy — dùng để phân biệt "tin nhắn mới" (turn mới)
# với "Steer" (turn hiện tại còn đang chạy). Set khi publish turn, xoá khi turn message.done.
# Xem docs/async-api-doc.md mục 5, docs/api-doc.md mục 2.1.
AGENT_ACTIVE_TURN_KEY = "agent:active_turn:{conversation_id}"

# Giá trị = `TurnRequest` JSON của turn/resume đã persist nhưng CHƯA đẩy vào
# `agent_request_queue` — Core hoãn publish tới khi client thực sự mở SSE (`GET
# .../stream`) để không mất event đầu luồng (Redis Pub/Sub không replay). Handler SSE
# `GETDEL` key này ngay sau khi `subscribe` xong rồi mới publish cho Worker.
# Xem docs/async-api-doc.md mục 1 + 6.
AGENT_PENDING_TURN_KEY = "agent:pending_turn:{conversation_id}"

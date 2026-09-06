# Quy ước coding — Backend (core/)

Tài liệu này là quy ước chi tiết khi viết code trong `core/`. Xem `../README.md` để biết cách
chạy dev; xem `../../docs/kien-truc-he-thong.md` cho bức tranh toàn hệ thống, `api-doc.md` /
`async-api-doc.md` cho đặc tả API, `db-diagram.md` cho schema DB.

## 1. Vai trò từng layer (`app/`)

| Thư mục | Vai trò | KHÔNG được làm |
|---|---|---|
| `app/core/` | Cấu hình (`config.py`), hằng số queue/channel (`constants.py`) | Không chứa logic nghiệp vụ |
| `app/db/` | Engine/session SQLAlchemy (`session.py`), `DeclarativeBase` (`base.py`) | Không import FastAPI/route |
| `app/models/` | ORM model (SQLAlchemy) — ánh xạ bảng DB | Không được lộ ra ngoài API (xem mục 3) |
| `app/dto/` | Pydantic model — hợp đồng request/response của API | Không import ORM model |
| `app/infra/` | Client hạ tầng dùng chung: `redis_client.py`, `rabbitmq_client.py` | Không chứa logic nghiệp vụ cụ thể 1 resource |
| `app/agent/` | LangGraph reasoning loop + LLM (`llm.py`, `graph.py`) + worker tiến trình riêng (`worker.py`) | Không import FastAPI (worker chạy độc lập với Core) |
| `app/api/` | FastAPI router — nhận request, gọi service/repository, trả DTO | Không viết SQL/logic nghiệp vụ trực tiếp trong route (khi có `app/services/`) |

Khi thêm domain thật (conversation, message...), tạo thêm `app/services/` (business logic) và
`app/repositories/` (truy vấn DB), theo đúng thứ tự gọi:

```
route (app/api) → service (app/services) → repository (app/repositories) → model (app/models)
                        ↑ nhận/trả DTO           ↑ nhận/trả model (ORM)
```

## 2. DTO (Pydantic) vs Model (SQLAlchemy) — bắt buộc tách biệt

- **DTO** (`app/dto/`): dùng làm kiểu tham số route (request) và `response_model`/kiểu trả về
  (response). Là **hợp đồng API**, độc lập với thiết kế DB, có thể versioning riêng.
- **Model** (`app/models/`): ORM, ánh xạ bảng DB, chỉ dùng trong `repositories`/`services`.
- **Không bao giờ** trả thẳng 1 SQLAlchemy model object ra route — luôn convert sang DTO
  (`XxxOutput.model_validate(model_obj)` hoặc field-by-field trong service).
- Ví dụ tối thiểu, xem `app/dto/health.py` + `app/api/health.py`.

### Envelope response

Toàn bộ response list/object dùng chung envelope `{"data": ...}` qua `ApiResponse[T]` /
`PageResponse[T]` trong `app/dto/common.py`:

```python
from app.dto.common import ApiResponse

@router.get("/items/{id}", response_model=ApiResponse[ItemOutput])
async def get_item(id: str, ...) -> ApiResponse[ItemOutput]:
    item = await item_service.get(id)
    return ApiResponse(data=ItemOutput.model_validate(item))
```

Ngoại lệ: endpoint cần tự set status code khác 200 theo điều kiện (vd `/health/ready` trả
200/503) thì build DTO thủ công rồi `JSONResponse(status_code=..., content=dto.model_dump())`
thay vì dùng `response_model` — xem `app/api/health.py`.

## 3. Async — mọi I/O phải `async def`

- DB: luôn dùng `AsyncSession` qua dependency `get_db` (`app/db/session.py`), không tạo
  session mới bằng tay trong route — **ngoại lệ duy nhất**: `/health/ready` tự mở session
  ngắn hạn để tự kiểm tra kết nối DB (đây là health-check hạ tầng, không phải truy vấn
  domain, nên không cần vòng đời request-scoped qua DI — xem mục 4 để hiểu vì sao domain
  route thì bắt buộc dùng `Depends(get_db)`).
- Redis/RabbitMQ: dùng client dùng chung trong `app/infra/`, không tự tạo connection mới ở
  nơi khác.
- Không gọi hàm sync blocking (network, `time.sleep`, driver DB sync...) trong `async def` —
  sẽ block event loop của toàn bộ server.

## 4. Dependency Injection (FastAPI `Depends`)

**Có** — bắt buộc dùng `Depends` cho mọi resource route cần, ngay cả khi hiện tại chỉ có
`get_db` (`app/db/session.py`) là dependency thật sự tồn tại và **chưa route nào dùng tới**
(vì chưa có domain route). Lý do cần quy ước này từ bây giờ:

- **Session DB phải request-scoped.** `get_db()` mở 1 `AsyncSession` mới, tự đóng khi request
  kết thúc (kể cả khi lỗi, nhờ `async with`). Nếu route tự gọi `AsyncSessionLocal()` (như
  `/health/ready` đang làm — xem ngoại lệ ở mục 3), mỗi chỗ phải tự nhớ đóng session đúng
  cách; dễ leak connection khi code domain phình ra nhiều route.
- **Test được.** FastAPI cho override dependency bằng
  `app.dependency_overrides[get_db] = fake_get_db` khi viết test — route không cần biết gì
  thay đổi. Nếu route tự import `AsyncSessionLocal`/`redis_client`/`rabbitmq_client` trực
  tiếp, không có chỗ nào để "chèn" bản giả lập khi test.
- **Signature route tự khai báo nó cần gì.** Đọc `def get_item(db: AsyncSession = Depends(get_db))`
  là biết ngay route đụng DB — không cần đọc hết thân hàm.
- **Compose được nhiều tầng.** Khi có `app/services/`, `service` cũng nhận dependency qua
  hàm provider (`get_xxx_service`), route chỉ `Depends(get_xxx_service)` — FastAPI tự dựng
  cây dependency (route → service → repository → db session), giống pattern
  `dependencies/provider.py` của bản thiết kế trước đây trong dự án.

### Quy ước cụ thể

- **DB session**: route/service cần DB luôn khai báo tham số
  `db: AsyncSession = Depends(get_db)` — không `AsyncSessionLocal()` tay (trừ ngoại lệ ở mục 3).
  `get_db()` tự `commit()` khi request xử lý xong không lỗi, tự `rollback()` khi có
  exception (Unit of Work — 1 request = 1 transaction) — repository chỉ `flush()`,
  **không** tự `commit()`/`rollback()`.
- **Service/Repository** (khi thêm `app/services/`, `app/repositories/`): mỗi service có 1
  hàm provider `get_xxx_service(db: AsyncSession = Depends(get_db)) -> XxxService`, route
  dùng `Depends(get_xxx_service)`. Đặt các hàm provider trong `app/api/deps.py` (tạo khi cần)
  hoặc ngay cạnh class service nếu ít route dùng.
- **Redis/RabbitMQ client**: `redis_client`/`rabbitmq_client` trong `app/infra/` là
  **singleton dùng chung cả process** (connection pool, không phải resource per-request) —
  KHÔNG cần bọc qua `Depends` để tạo mới mỗi request, cứ `from app.infra.xxx import xxx`
  thẳng. Chỉ cần thêm 1 hàm `get_redis_client()`/`get_rabbitmq_client()` mỏng (trả về
  singleton có sẵn) nếu 1 route cụ thể cần mock nó trong test qua `dependency_overrides` —
  không làm sẵn khi chưa có nhu cầu thật (tránh over-engineering).
- **Settings** (`app/core/config.py`): `settings` cũng là singleton (`@lru_cache`), import
  thẳng `from app.core.config import settings`, không cần `Depends` (cấu hình không đổi theo
  từng request).

## 5. Cấu hình — không `os.getenv` rải rác

Mọi biến môi trường khai báo tập trung trong `app/core/config.py` (`Settings`, đọc từ `.env`
qua `pydantic-settings`). Nơi khác luôn `from app.core.config import settings`, không gọi
`os.getenv` trực tiếp (trừ chính `config.py`).

Tên queue (RabbitMQ) / channel (Redis) là hằng số trong `app/core/constants.py`, không hard
code string queue name rải rác trong code.

## 6. Type checking — Pyright strict

```bash
uv run pyright app main.py
```

- `pyproject.toml` set `typeCheckingMode = "strict"`.
- Chấp nhận `reportUnknownMemberType`/`reportMissingTypeArgument` phát sinh từ thư viện
  thiếu type stub đầy đủ (`redis`, `aio-pika`, `langgraph`) — đây là hạn chế của thư viện,
  không phải lỗi code. Không cần thêm `# pyright: ignore` cho từng dòng trừ khi lỗi đó che
  mất 1 lỗi thật khác.
- Mọi lỗi khác (đặc biệt `reportArgumentType`, `reportGeneralTypeIssues`) phải fix trước khi
  coi 1 thay đổi là xong.

## 7. Quy trình thêm thành phần mới

### Model SQLAlchemy mới
1. Tạo file trong `app/models/`, kế thừa `Base` (`app/db/base.py`).
2. Import trong `app/models/__init__.py` — bắt buộc, nếu không `Base.metadata.create_all`
   (dev) và Alembic (prod, sau này) sẽ không thấy bảng.

### DTO mới
1. Tạo file `app/dto/<resource>.py`, ví dụ `app/dto/conversation.py`.
2. Đặt tên: `<Resource>Input` (request), `<Resource>Output` (response item). Dùng
   `ApiResponse[<Resource>Output]` / `PageResponse[<Resource>Output]` làm `response_model`.

### Endpoint mới
1. Router trong `app/api/<resource>.py`, `APIRouter(tags=["<resource>"])`.
2. `include_router(..., prefix=settings.API_V1_PREFIX)` trong `main.py`.
3. Request/response phải qua DTO (mục 2) — không nhận/trả `dict` tay ngoại trừ trường hợp
   như `/health/ready` (mục 2, phần ngoại lệ).
4. Resource nào (DB, service...) thì khai báo qua `Depends(...)` (mục 4) — không import
   thẳng session/service vào thân hàm route.

### Kênh Redis Pub/Sub mới
1. Thêm tên channel vào `app/core/constants.py` (format string nếu có tham số, vd
   `"agent:events:{conversation_id}"`).
2. Publish: `from app.infra.redis_client import publish`.
3. Subscribe: `async for msg in subscribe(channel)` hoặc `psubscribe(pattern)`.

### Queue RabbitMQ mới
1. Thêm tên queue vào `app/core/constants.py`.
2. Publish: `await rabbitmq_client.publish(queue, body_bytes)`.
3. Consume: `await rabbitmq_client.consume(queue, handler)` với
   `handler: Callable[[AbstractIncomingMessage], Awaitable[None]]`, tự
   `async with message.process():` bên trong handler.

### Node reasoning mới trong Agent (LangGraph)
1. Thêm hàm node trong `app/agent/graph.py`, nhận `AgentState`, trả `dict` chứa field cần
   update (LangGraph merge theo key — field không có reducer trong `AgentState` sẽ bị ghi đè
   toàn bộ, không cộng dồn, trừ `messages` đã có `add_messages` reducer).
2. Nối node bằng `graph.add_node(...)` / `graph.add_edge(...)` /
   `graph.add_conditional_edges(...)` trong `build_agent_graph()`.
3. Cần LLM có tool: dùng `get_llm_with_tools([...])` (`app/agent/llm.py`) thay `get_llm()`.

## 8. Naming

- File/module: `snake_case.py`.
- Class (DTO, model, service...): `PascalCase`.
- Hằng số (queue/channel name, default value): `UPPER_SNAKE_CASE`, khai báo ở
  `app/core/constants.py` hoặc đầu file liên quan.
- Biến môi trường: `UPPER_SNAKE_CASE`, khai báo trong `Settings` (`app/core/config.py`).
- DTO: `<Resource>Input` / `<Resource>Output` (không dùng hậu tố `DTO`/`Dto`).
- Provider DI: `get_<thứ cần lấy>` (vd `get_db`, `get_conversation_service`).

## 9. Docstring & comment

- Mỗi module mới bắt đầu bằng 1 docstring ngắn nói rõ **vai trò** file đó trong hệ thống
  (không mô tả lại từng dòng code bên dưới).
- Comment tiếng Việt, ngắn gọn, giải thích **tại sao** (why) hơn là **cái gì** (what) — code
  đã tự nói "cái gì" nếu đặt tên rõ ràng.

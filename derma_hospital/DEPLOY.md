# Deploy production bằng `docker-compose.prod.yml`

Hướng dẫn dựng toàn bộ stack (Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO + Core API + Agent
Worker + FE) trong Docker và nạp đủ dữ liệu. Tunnel/reverse-proxy (Cloudflare Tunnel, nginx…) tự
cấu hình riêng, trỏ vào cổng `3000` của `derma-fe`.

## 1. Kiến trúc container

| Service | Vai trò | Ghi chú |
|---|---|---|
| `derma-fe` | Next.js, **cổng 3000 publish ra host** | Tự proxy `/api/v1/*` sang `derma-core-api` |
| `derma-core-api` | FastAPI (REST + SSE) | Cổng 3050, chỉ trong mạng Docker |
| `agent-worker` | LangGraph agent | Cùng image với core-api, khác `command` |
| `postgres` `redis` `rabbitmq` `qdrant` `neo4j` `minio` | Hạ tầng | Không publish port ra host |

Các container gọi nhau bằng **tên service** (DNS nội bộ Docker), không dùng `localhost`.
`docker-compose.prod.yml` tự ghi đè các biến kết nối (`DATABASE_URL`, `NEO4J_URL`, …) lên
`core/.env`, nên bạn không cần sửa chúng.

## 2. Chuẩn bị (làm 1 lần)

### 2.1. Đảm bảo đủ file trên máy deploy

Các file sau **phải có** trước khi build, kiểm tra kỹ vì có file không nằm trong git:

| File | Trong git? | Ghi chú |
|---|---|---|
| `core/data/primekg/derma_nodes.csv`, `derma_edges.csv` | Có (sau khi sửa `.gitignore`) | ~48MB, nạp Neo4j |
| `core/data/dermo/dermo_kg.json` | Có | Nạp Neo4j |
| `core/knowledge_base/data/chunks/all_chunks.json` | Có | Nạp Qdrant (435 chunk) |
| `model/model_output/AdaptiveCNN_SkinDisease_v5_best.pth` | **Chưa** (44MB) | Nếu thiếu, `docker build` core lỗi ở bước `COPY`. Commit hoặc copy tay lên server |
| `fe/pnpm-workspace.yaml` | Có | Bắt buộc, thiếu thì `pnpm install` lỗi |
| `.env`, `core/.env` | **Không** (ignore) | Tạo ở bước 2.2 và 2.3 |

### 2.2. File `.env` ở thư mục gốc (mật khẩu hạ tầng)

```bash
cp .env.prod.example .env
```

Điền mật khẩu. Sinh chuỗi random: `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`.

**Các giá trị bị từ chối (container crash-loop):**
- `NEO4J_PASSWORD` **không được** là `neo4j`.
- `MINIO_ROOT_PASSWORD` phải **≥ 8 ký tự**, `MINIO_ROOT_USER` ≥ 3 ký tự.

> Mật khẩu Postgres/RabbitMQ/Neo4j/MinIO chỉ có hiệu lực **lần đầu** khi volume được tạo. Đổi sau đó
> không ăn (xem mục 6, "Đổi mật khẩu").

### 2.3. File `core/.env` (cấu hình ứng dụng)

```bash
cp core/.env.example core/.env
```

Điền tối thiểu:

| Biến | Giá trị |
|---|---|
| `OPENROUTER_API_KEY` | Key từ https://openrouter.ai/keys |
| `AGENT_MODEL` | Mặc định `openai:google/gemma-4-26b-a4b-it` (bản **trả phí**, cần credit OpenRouter; bản `:free` bị chặn khi dùng tool-calling) |
| `APP_ACCESS_TOKEN` | Mã truy cập gửi cho người test. Để trống = tắt xác thực |

Không cần sửa `DATABASE_URL`, `NEO4J_URL`, `MINIO_*`, … — compose tự ghi đè.
Không cần `GOOGLE_API_KEY` (embedding chạy local).

## 3. Khởi chạy

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Lần build đầu mất vài phút (image core ~ vài GB do torch + model embedding được tải sẵn vào image).
Kiểm tra:

```bash
docker compose -f docker-compose.prod.yml ps
```

Cả 9 container phải `Up`; `postgres`, `redis`, `rabbitmq`, `neo4j`, `minio` phải `healthy`.

## 4. Nạp dữ liệu (bắt buộc — DB mới hoàn toàn trống)

```bash
./reset-and-gen-data.sh
```

Script chạy trong container `derma-core-api`, nạp 3 nguồn:

| Nguồn | Đích | Dùng bởi |
|---|---|---|
| Guideline BYT/WHO/MedlinePlus (435 chunk) | Qdrant | `search_disease_guidelines`, `get_disease_guideline_profile` |
| PrimeKG (36k node, 474k cạnh) | Neo4j | `query_dermatology_kg`, `ground_medical_entities` |
| DermO (3.4k thuật ngữ) | Neo4j | `lookup_dermo_term`, `ground_medical_entities` |

- Chạy lại nhiều lần không sao (idempotent).
- `./reset-and-gen-data.sh --reset` — **xoá sạch** rồi nạp lại từ đầu (dùng khi đổi dữ liệu/model embedding).
- Mất khoảng 1–2 phút. Phải chạy **sau khi** `derma-core-api` đã start.

Nếu thiếu bước này agent vẫn chạy nhưng các tool tra cứu trả về rỗng, câu trả lời sẽ nghèo/sai.

## 5. Kiểm tra sau khi chạy

```bash
# 1. FE proxy tới backend được không (kỳ vọng {"status":"ok"})
curl -s http://localhost:3000/api/v1/health

# 2. Tạo hội thoại (kỳ vọng HTTP 201). Nếu đã bật APP_ACCESS_TOKEN thì thêm header:
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3000/api/v1/conversations \
  -H "Authorization: Bearer <APP_ACCESS_TOKEN>" -H "Content-Type: application/json" \
  -d '{"userId":"user-1","initMessage":"","title":"test"}'

# 3. Dữ liệu đã nạp
docker compose -f docker-compose.prod.yml exec -T derma-core-api python -c "
import asyncio
from app.infra.qdrant_client import client
from app.core.config import settings
async def m(): print('Qdrant KB points:', (await client.count(settings.QDRANT_KB_COLLECTION)).count)
asyncio.run(m())"          # kỳ vọng 435
```

Rồi mở `http://<host>:3000`, nhập mã `APP_ACCESS_TOKEN` ở màn hình đầu tiên, gửi thử một tin nhắn.

## 6. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `minio` / `neo4j` restart liên tục | Mật khẩu không hợp lệ (mục 2.2) | Sửa `.env` rồi `docker compose -f docker-compose.prod.yml up -d minio neo4j` |
| Đổi mật khẩu Neo4j/Postgres mà không có tác dụng | Chỉ áp dụng khi tạo volume lần đầu | Xoá volume của service đó (`docker compose -f docker-compose.prod.yml down`, `docker volume rm derma-hospital-prod_<tên>_data`) rồi `up`, nạp lại data. **Mất dữ liệu** |
| FE gọi API lỗi `ECONNREFUSED 127.0.0.1:3050` (500 ở `/api/v1/...`) | `BACKEND_URL` được **bake lúc `next build`** (build arg), env runtime không có tác dụng | Đổi `args.BACKEND_URL` của `derma-fe` rồi `up -d --build derma-fe` |
| `POST /conversations` → 500 `fk_conversations_user_id_users` | Thiếu user `user-1` (FE hard-code) | Core tự tạo user này khi khởi động; chỉ cần build lại/khởi động lại `derma-core-api` bản mới |
| API trả `401 Thiếu hoặc sai access token` | Đã bật `APP_ACCESS_TOKEN` | Gửi header `Authorization: Bearer <token>`; FE sẽ hiện màn hình nhập mã |
| Chat trả "hệ thống gặp sự cố…" | LLM lỗi (hết credit OpenRouter, rate limit, sai key) | Xem `docker compose -f docker-compose.prod.yml logs agent-worker` |
| Tool tra cứu trả rỗng | Chưa nạp data | Chạy `./reset-and-gen-data.sh` |
| `docker build` core lỗi `COPY model/...: not found` | Thiếu checkpoint CNN | Xem mục 2.1 |
| `pnpm install` lỗi `ERR_PNPM_IGNORED_BUILDS` | Thiếu `fe/pnpm-workspace.yaml` (`allowBuilds`) | Đảm bảo file này có trong build context |

Xem log: `docker compose -f docker-compose.prod.yml logs -f derma-core-api agent-worker`.

## 7. Vận hành thường ngày

```bash
# Cập nhật code
git pull
docker compose -f docker-compose.prod.yml up -d --build          # build lại những service đổi

# Chỉ đổi prompt/code agent
docker compose -f docker-compose.prod.yml up -d --build derma-core-api agent-worker

# Dừng (giữ dữ liệu)
docker compose -f docker-compose.prod.yml down

# Dừng và XOÁ TOÀN BỘ dữ liệu (Postgres, Qdrant, Neo4j, MinIO, ...)
docker compose -f docker-compose.prod.yml down -v
```

Dữ liệu nằm trong các named volume (`postgres_data`, `qdrant_data`, `neo4j_data`, `minio_data`, …);
`down` không xoá, `down -v` mới xoá.

## 8. Lưu ý bảo mật

- Chỉ `derma-fe:3000` publish ra host. Đặt tunnel/reverse-proxy phía trước và dùng HTTPS.
- `APP_ACCESS_TOKEN` chỉ là token chung dùng chung, phù hợp demo/test, **không phải** hệ thống
  đăng nhập. FE vẫn hard-code user `user-1` nên mọi người dùng chung một tài khoản và chung memory.
- Không commit `.env` và `core/.env` (đã được ignore).

# .gemini — Hướng dẫn và Kỹ năng dành cho Gemini / AI Assistant

Thư mục này chứa các quy tắc, tài liệu hướng dẫn và bộ kỹ năng (Skills) dành riêng cho Gemini khi làm việc trong dự án **Derma Hospital (DATN-2026)**.

---

## 📂 Danh mục Kỹ năng (Skills)

Các bộ kỹ năng dưới đây định nghĩa chi tiết kiến trúc, quy chuẩn code và cách thức vận hành của từng phần trong dự án:

| Tên kỹ năng | Thư mục | Mô tả |
| :--- | :--- | :--- |
| **`derma-fe-conventions`** | `skills/derma-fe-conventions/` | Quy ước Frontend Next.js 16 (App Router, Zustand store, TanStack Query, Radix UI, Tailwind CSS v4). |
| **`derma-core-conventions`** | `skills/derma-core-conventions/` | Quy ước Backend FastAPI (Entity `dto/base`, models, services, repositories, tools agent). |
| **`derma-pipeline-conventions`** | `skills/derma-pipeline-conventions/` | Quy ước Pipeline số hóa sách giáo khoa da liễu (`ingest` → `toc` → `chunks` → `index`). |
| **`experiment-agent-flow`** | `skills/experiment-agent-flow/` | Hướng dẫn thử nghiệm luồng suy luận ReAct của Agent LangGraph, prompt và tools. |
| **`run-core`** | `skills/run-core/` | Lệnh và quy trình khởi chạy, kiểm tra và debug Backend & Agent Worker. |
| **`run-fe`** | `skills/run-fe/` | Lệnh khởi chạy, kiểm tra kiểu (`pnpm tsc --noEmit`) và debug Frontend. |

---

## 📌 File quy ước chính cần tuân thủ

1. [AGENTS.md](file:///c:/Users/dell/Documents/CODE/DATN-2026/AGENTS.md): Bản quy tắc tổng thể toàn dự án (Bối cảnh Đồ án tốt nghiệp 2026, 2 hệ thống lớn, luồng SSE + RabbitMQ, kiến trúc DB và nguyên tắc bất biến).
2. [fe/AGENTS.md](file:///c:/Users/dell/Documents/CODE/DATN-2026/fe/AGENTS.md): Quy chuẩn riêng biệt cho Frontend Next.js.
3. [thi_t_k_database.md](file:///c:/Users/dell/Documents/CODE/DATN-2026/thi_t_k_database.md): Thiết kế chi tiết cơ sở dữ liệu (PostgreSQL, MinIO, Qdrant, Neo4j).

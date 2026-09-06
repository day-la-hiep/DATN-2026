"""DTO (Pydantic) — hợp đồng dữ liệu vào/ra API, tách biệt khỏi ORM model (`app/models/`).

Quy ước:
  - **Request DTO**: khai báo làm kiểu tham số trong route (`body: XxxInput`) — FastAPI
    tự parse + validate từ JSON body/query trước khi vào hàm.
  - **Response DTO**: dùng làm `response_model` (hoặc build thủ công rồi `model_dump()`
    khi cần tự kiểm soát status code) — FastAPI serialize + lọc field thừa, đồng thời
    sinh đúng OpenAPI schema cho Swagger UI (`/docs`).
  - DTO KHÔNG import SQLAlchemy model. Chiều chuyển đổi luôn là
    schema (ORM, `app/models/`) -> DTO (response), do route/service đảm nhiệm.
  - Mỗi resource 1 file, vd `app/dto/health.py`; DTO dùng chung (envelope, phân trang...)
    đặt trong `app/dto/common.py`.
"""

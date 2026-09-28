# Image dùng chung cho CẢ 2 tiến trình Core (FastAPI) và Agent Worker — cùng
# codebase/dependency, chỉ khác lệnh chạy (xem `docker-compose.prod.yml` mục
# `core-api`/`agent-worker`, `command:` override).
#
# QUAN TRỌNG — build context phải là REPO ROOT (không phải core/), vì cần COPY thêm
# checkpoint model từ ../model/ (sibling repo root, xem app/core/config.py::
# SKIN_CNN_CHECKPOINT_PATH):
#   docker build -f core/Dockerfile -t derma-core .
# (docker-compose.prod.yml đã cấu hình đúng context/dockerfile này.)

FROM python:3.12-slim

# uv: package manager dùng xuyên suốt dự án (core/pyproject.toml + core/uv.lock).
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /usr/local/bin/

WORKDIR /app

# libgomp1: runtime dependency của torch (OpenMP) trên slim image.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# `uv sync` cần TOÀN BỘ source có mặt trước (pyproject.toml của project này không đánh
# dấu `[tool.uv] package = false` — uv coi đây là package thật, cố cài editable, cần
# `app/` tồn tại) — copy source TRƯỚC rồi mới sync, không tách layer "chỉ deps" như
# thường thấy (đổi lại: sửa code cũng phải chạy lại `uv sync`, chấp nhận được vì
# `uv sync --frozen` chỉ resolve lại nếu `uv.lock` đổi, rất nhanh khi cache hit).
COPY core/ .
# Mặc định uv timeout 30s/request và ít retry -> mirror PyPI chậm (Aliyun/TUNA) hay làm
# `uv sync` fail giữa chừng ("Failed to download ... network timeout", exit 1). Tăng lên.
ENV UV_HTTP_TIMEOUT=300 \
    UV_HTTP_RETRIES=8
RUN uv sync --frozen --no-dev

# Checkpoint CNN (model/model_output/, sibling repo root) — không copy vào core/ để
# tránh trùng lặp file nặng (44MB) trong source tree, xem docstring
# app/agent/tools/skin_image_classifier.py.
COPY model/model_output/AdaptiveCNN_SkinDisease_v5_best.pth /model/model_output/AdaptiveCNN_SkinDisease_v5_best.pth

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    SKIN_CNN_CHECKPOINT_PATH=/model/model_output/AdaptiveCNN_SkinDisease_v5_best.pth

# Bake model embedding local (sentence-transformers, app/agent/embeddings.py) vào
# image lúc build — tránh tải ~470MB từ HuggingFace Hub lúc container khởi động lần
# đầu (chậm/lỗi nếu mạng prod hạn chế). Cần GOOGLE_API_KEY/OPENROUTER_API_KEY KHÔNG bắt
# buộc ở bước này (chỉ load embedding model, không gọi LLM).
RUN /app/.venv/bin/python -c "from agent.embeddings import _get_model; _get_model()"

EXPOSE 3050

# Mặc định chạy Core API — Agent Worker override command trong compose.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3050"]

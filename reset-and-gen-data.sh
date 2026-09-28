#!/usr/bin/env bash
# Reset + nạp lại TOÀN BỘ dữ liệu tĩnh cho stack PROD (docker-compose.prod.yml):
#   - Qdrant: knowledge base guideline da liễu (BYT 75/2015, WHO, MedlinePlus)
#     -> core/data-ingest/01_normalize/scripts/load_knowledge_base.py
#   - Neo4j:  PrimeKG (quan hệ bệnh-triệu chứng-thuốc) -> core/data-ingest/01_normalize/scripts/load_primekg.py
#   - Neo4j:  DermO (từ điển thuật ngữ da liễu)         -> core/data-ingest/01_normalize/scripts/load_dermo.py
#
# Cả 3 script chạy BÊN TRONG container `derma-core-api` (đã có sẵn code + data +
# dependency, đọc đúng NEO4J_URL/QDRANT_URL nội bộ Docker network từ compose) — không
# cần cài gì thêm trên host, không cần publish port Neo4j/Qdrant ra ngoài.
#
# Chạy SAU KHI `docker compose -f docker-compose.prod.yml up -d --build` đã xong và
# service `derma-core-api` đã start (script tự chờ vài giây nếu chưa sẵn sàng).
#
# Dùng:
#   ./reset-and-gen-data.sh            # chỉ ingest/upsert thêm (idempotent, an toàn chạy lại)
#   ./reset-and-gen-data.sh --reset    # xoá sạch dữ liệu cũ trước khi nạp lại từ đầu

set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
SERVICE="derma-core-api"
RESET_FLAG=()

if [[ "${1:-}" == "--reset" ]]; then
  RESET_FLAG=(--reset)
  echo "!! Chế độ --reset: sẽ XOÁ SẠCH dữ liệu cũ (Qdrant KB collection + Neo4j PrimeKG/DermO) trước khi nạp lại."
fi

run() {
  echo "==> $*"
  docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" "$@"
}

echo "── Qdrant: knowledge base guideline ──────────────────────────"
run python data-ingest/01_normalize/scripts/load_knowledge_base.py "${RESET_FLAG[@]}"

echo "── Neo4j: PrimeKG ─────────────────────────────────────────────"
run python data-ingest/01_normalize/scripts/load_primekg.py "${RESET_FLAG[@]}"

echo "── Neo4j: DermO ────────────────────────────────────────────────"
run python data-ingest/01_normalize/scripts/load_dermo.py "${RESET_FLAG[@]}"

echo "Hoàn tất."

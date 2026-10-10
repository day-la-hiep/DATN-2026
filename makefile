.PHONY: infra infra-down backend worker ingest-worker migrate migrate-new init-db load-primekg load-dermo load-kg frontend

infra:
	docker compose up -d

infra-down:
	docker compose down

backend:
	cd core && uv run python main.py

worker:
	cd core && uv run python -u -m agent.worker

ingest-worker:
	cd core && uv run python -u -m app.workers.document_ingest_worker

migrate:
	cd core && uv run alembic upgrade head

migrate-new:
	cd core && uv run alembic revision --autogenerate -m "$(m)"

# bucket MinIO + dữ liệu mẫu (user-1, bác sĩ, admin); chạy sau migrate, chạy lại không tạo trùng
init-db:
	cd core && uv run python scripts/init_db.py

# nạp PrimeKG (label :Entity — quan hệ bệnh/triệu chứng/thuốc) vào Neo4j; chạy lại được, `make load-primekg reset=1` xoá :Entity cũ trước khi nạp
load-primekg:
	cd core && uv run python data_ingest/01_normalize/scripts/load_primekg.py $(if $(reset),--reset)

# nạp ontology thuật ngữ DermO vào Neo4j (nhánh KG của hybrid_retrieval); chạy lại được, `make load-dermo reset=1` xoá DermO cũ trước khi nạp
load-dermo:
	cd core && uv run python data_ingest/01_normalize/scripts/load_dermo.py $(if $(reset),--reset)

# nạp đủ knowledge graph cho tool KG: PrimeKG + DermO (thiếu một trong hai thì query báo label không tồn tại)
load-kg: load-primekg load-dermo

frontend:
	cd fe && pnpm dev

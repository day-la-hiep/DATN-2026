.PHONY: infra infra-down backend worker migrate migrate-new init-db frontend

infra:
	docker compose up -d

infra-down:
	docker compose down

backend:
	cd core && uv run python main.py

worker:
	cd core && uv run python -u -m agent.worker

migrate:
	cd core && uv run alembic upgrade head

migrate-new:
	cd core && uv run alembic revision --autogenerate -m "$(m)"

# bucket MinIO + dữ liệu mẫu (user-1, bác sĩ, admin); chạy sau migrate, chạy lại không tạo trùng
init-db:
	cd core && uv run python scripts/init_db.py

frontend:
	cd fe && pnpm dev

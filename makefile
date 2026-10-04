.PHONY: infra infra-down backend worker migrate migrate-new frontend

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

frontend:
	cd fe && pnpm dev

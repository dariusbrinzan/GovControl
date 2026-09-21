.PHONY: api-check api-dev api-test db-migrate db-up db-down db-logs db-seed db-status

api-dev:
	cd apps/api && uv run uvicorn app.main:app --reload

api-test:
	cd apps/api && uv run pytest

api-check:
	cd apps/api && uv run ruff check . && uv run mypy app

db-migrate:
	cd apps/api && uv run alembic upgrade head

db-seed:
	cd apps/api && uv run python -m app.scripts.seed_development_data

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres

db-status:
	docker compose ps

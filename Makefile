.PHONY: api-check api-dev api-test db-migrate db-up db-down db-logs db-seed db-status web-build web-check web-dev web-test web-test-e2e

api-dev:
	cd apps/api && uv run uvicorn app.main:app --reload

api-test:
	cd apps/api && uv run pytest

api-check:
	cd apps/api && uv run ruff check . && uv run mypy app

web-dev:
	cd apps/web && npm run dev

web-build:
	cd apps/web && npm run build

web-check:
	cd apps/web && npm run lint && npm run typecheck && npm test && npm run build

web-test:
	cd apps/web && npm test

web-test-e2e:
	cd apps/web && npm run test:e2e

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

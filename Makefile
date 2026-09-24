.PHONY: api-check api-dev api-test contracts-check contracts-dev contracts-migrate contracts-test db-migrate db-up db-down db-logs db-seed db-status platform-up web-build web-check web-dev web-test web-test-e2e

api-dev:
	cd apps/api && uv run uvicorn app.main:app --reload

api-test:
	cd apps/api && uv run pytest

api-check:
	cd apps/api && uv run ruff check . && uv run mypy app

contracts-dev:
	cd apps/contracts-api && uv run uvicorn contracts_app.main:app --reload --port 8010

contracts-test:
	cd apps/contracts-api && uv run pytest

contracts-check:
	cd apps/contracts-api && uv run ruff check . && uv run mypy contracts_app && uv run pytest

contracts-migrate:
	cd apps/contracts-api && uv run alembic upgrade head

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

platform-up:
	docker compose up -d postgres redis minio

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres

db-status:
	docker compose ps

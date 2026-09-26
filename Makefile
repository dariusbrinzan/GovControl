.PHONY: api-check api-dev api-test contracts-check contracts-dev contracts-migrate contracts-seed contracts-test contracts-worker db-migrate db-up db-down db-logs db-seed db-status documents-backfill documents-check documents-dev documents-export-legacy documents-migrate documents-test documents-worker gateway-check gateway-dev gateway-test platform-up stack-check stack-down stack-logs stack-status stack-up stack-up-debug web-build web-check web-dev web-test web-test-e2e web-test-e2e-live

DOCUMENT_EXPORT_DIR ?= /tmp/govcontrol-documents-export

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

contracts-seed:
	cd apps/contracts-api && uv run python -m contracts_app.seed

contracts-worker:
	cd apps/contracts-api && uv run python -m contracts_app.worker

documents-dev:
	cd apps/documents-api && uv run uvicorn documents_app.main:app --reload --port 8020

documents-test:
	cd apps/documents-api && uv run pytest

documents-check:
	cd apps/documents-api && uv run ruff check . && uv run mypy documents_app && uv run pytest && uv run alembic check

documents-migrate:
	cd apps/documents-api && uv run alembic upgrade head

documents-worker:
	cd apps/documents-api && uv run python -m documents_app.worker

documents-export-legacy:
	cd apps/api && uv run python -m app.scripts.export_legacy_documents --output "$(DOCUMENT_EXPORT_DIR)"

documents-backfill:
	cd apps/documents-api && uv run python -m documents_app.backfill --input "$(DOCUMENT_EXPORT_DIR)"

gateway-dev:
	cd apps/gateway && uv run uvicorn gateway_app.main:app --reload --port 8080

gateway-test:
	cd apps/gateway && uv run pytest

gateway-check:
	cd apps/gateway && uv run ruff check . && uv run mypy gateway_app && uv run pytest

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

web-test-e2e-live:
	set -a; . ./.env; set +a; cd apps/web && npm run test:e2e -- live-contracts.spec.ts live-documents.spec.ts live-legal.spec.ts --workers=1

db-migrate:
	cd apps/api && uv run alembic upgrade head

db-seed:
	cd apps/api && uv run python -m app.scripts.seed_development_data

db-up:
	docker compose up -d postgres

platform-up:
	docker compose up -d postgres redis object-storage

db-down:
	docker compose stop postgres

db-logs:
	docker compose logs -f postgres

db-status:
	docker compose ps

stack-up:
	docker compose up -d --build

stack-up-debug:
	docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d --build

stack-down:
	docker compose down

stack-status:
	docker compose ps -a

stack-logs:
	docker compose logs -f gateway api contracts-api contracts-worker documents-api documents-worker web

stack-check:
	set -a; . ./.env; set +a; curl -fsS "http://127.0.0.1:$${GATEWAY_PORT:-8080}/ready"; curl -fsS "http://127.0.0.1:$${WEB_PORT:-3000}/" >/dev/null

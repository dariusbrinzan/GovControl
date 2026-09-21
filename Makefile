.PHONY: db-up db-down db-logs db-status

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres

db-status:
	docker compose ps

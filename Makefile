.PHONY: init up down logs generate backfill run psql test lint clean

START ?= 2026-09-01
DAYS  ?= 14

# first-time setup: folders owned by you (so Airflow can write), .env with your user id
init:
	mkdir -p logs data dags
	test -f .env || (cp .env.example .env && sed -i.bak "s/^AIRFLOW_UID=.*/AIRFLOW_UID=$$(id -u)/" .env && rm -f .env.bak)

up:
	docker compose up -d --build
	@echo "Airflow UI: http://localhost:8080  (admin / admin)"

down:
	docker compose down

logs:
	docker compose logs -f airflow-scheduler

# --- demo data + running without Airflow (needs: pip install -e ".[dev]") -------------
generate:
	python -m mediflow generate --start $(START) --days $(DAYS)

backfill:
	python -m mediflow backfill --start $(START) --end $$(date -d "$(START) + $$(( $(DAYS) - 1 )) days" +%F)

run:
	python -m mediflow run --date $(START)

psql:
	docker compose exec postgres psql -U warehouse -d warehouse

test:
	python -m pytest -q

clean:
	rm -rf data/raw data/clean data/rejected data/reference

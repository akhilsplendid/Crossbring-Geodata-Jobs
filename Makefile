SHELL := /usr/bin/env bash

DC := docker compose
DB_SVC := db
DB_USER := postgres
DB_NAME := jobsdb

.PHONY: up down logs psql init-db fetch-af load-csv map status

up:
	$(DC) -f docker-compose.yml up -d

down:
	$(DC) -f docker-compose.yml down -v

logs:
	$(DC) -f docker-compose.yml logs -f --tail=200

status:
	$(DC) -f docker-compose.yml ps

psql:
	$(DC) -f docker-compose.yml exec -T $(DB_SVC) psql -U $(DB_USER) -d $(DB_NAME)

init-db:
	$(DC) -f docker-compose.yml exec -T $(DB_SVC) psql -U $(DB_USER) -d $(DB_NAME) -f /scripts/01_init_postgis.sql

# Requires Python venv on host and PG_DATABASE_URL env var
fetch-af:
	python scripts/fetch_af_jobs.py --occupation-field apaJ_2ja_LuF --pages 5 --max-records 25

load-csv:
	python scripts/load_jobs_geodata.py --csv ../job_details_rows.csv

map:
	python viz/map_sample.py --out map.html --limit 2000


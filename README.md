Swedish Job Market Geodata Platform

Overview
- Loads `job_details_rows.csv` (47k+ postings) into PostgreSQL + PostGIS
- Validates and converts lon/lat to geometry (EPSG:4326)
- Adds spatial index, sample analytics queries, and a simple folium map

Prerequisites
- PostgreSQL 14+ with PostGIS installed
- Python 3.10+
- CSV file available at project root as `job_details_rows.csv` (or pass a path)

Setup
- Create DB and enable PostGIS:
  - psql -h localhost -U postgres -c "CREATE DATABASE jobsdb;"
  - psql -h localhost -U postgres -d jobsdb -f sql/01_init_postgis.sql
  - If you created the table earlier, rerun the script to ensure new columns exist.

- Python environment:
  - python -m venv .venv && . .venv/Scripts/Activate.ps1  (Windows PowerShell)
  - pip install -r requirements.txt

- Load data:
  - set PG_DATABASE_URL=postgresql+psycopg2://USER:PASS@localhost:5432/jobsdb
  - python scripts/load_jobs_geodata.py --csv ../job_details_rows.csv

- OPTIONAL: Ingest directly from Arbetsförmedlingen API (live data):
  - set PG_DATABASE_URL=postgresql+psycopg2://USER:PASS@localhost:5432/jobsdb
  - python scripts/fetch_af_jobs.py --occupation-field apaJ_2ja_LuF --pages 5 --max-records 25
    - Notes: uses POST search and GET detail per job; upserts into `jobs` with geometry.
    - You can supply a custom POST payload via `--payload-file payload.json`.
    - Example payload included: `payloads/af_search_example.json`

- Explore analytics:
  - psql -h localhost -U USER -d jobsdb -f sql/02_analytics_queries.sql

- Generate a simple map (HTML):
  - python viz/map_sample.py --out map.html --limit 2000

Schema Summary
- Table: jobs
  - id (PK), source_id, job_id, title, company, occupation, municipality, region,
    city, published_at, last_application_at, expiration_at, location geometry(Point,4326),
    lon, lat

Notes
- Coordinates are validated to be within [-180..180] for lon and [-90..90] for lat.
- Invalid or missing coordinates are skipped (count is logged).
- Geometry stored as `geometry(Point,4326)`. Use `::geography` cast for meter-based distances.

Verification / Demo
- One-command CSV demo: `make demo-csv` (starts DB, initializes schema, loads CSV, creates analytics, runs smoke test, writes `map.html`).
- One-command AF demo: `make demo-af` (fetches live AF jobs instead of CSV).
- Manual checks:
  - `make status` (containers up), `make psql` then run `SELECT COUNT(*) FROM jobs;` and `SELECT COUNT(*) FROM jobs WHERE location IS NOT NULL;`
  - `make analytics-sql` then try `SELECT * FROM nearby_jobs(18.0686, 59.3293, 50000) LIMIT 10;`
  - Open Adminer at http://localhost:8080 (server: db, user: postgres, pass: postgres, db: jobsdb)
  - Run `python scripts/smoke_test.py` to print PostGIS version, row counts, and a nearby sample.

Dashboard
- Run: make dashboard
- Open: http://localhost:8501


Containerized Dashboard
- Build & run with Docker: make dash-up
- Logs: make dash-logs
- Stop: make dash-down
- Open: http://localhost:8501


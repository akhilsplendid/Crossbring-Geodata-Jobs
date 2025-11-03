-- Enable PostGIS and create schema/table for jobs
CREATE EXTENSION IF NOT EXISTS postgis;

-- Main spatial table for jobs
CREATE TABLE IF NOT EXISTS public.jobs (
    id                 BIGSERIAL PRIMARY KEY,
    source_id          BIGINT,
    job_id             BIGINT,
    title              TEXT,
    company            TEXT,
    occupation         TEXT,
    employment_type    TEXT,
    work_time_extent   TEXT,
    duration           TEXT,
    positions          INTEGER,
    unspecified_workplace BOOLEAN,
    municipality       TEXT,
    region             TEXT,
    city               TEXT,
    street_address     TEXT,
    postal_code        TEXT,
    published_at       TIMESTAMP NULL,
    last_application_at TIMESTAMP NULL,
    expiration_at      TIMESTAMP NULL,
    lon                DOUBLE PRECISION,
    lat                DOUBLE PRECISION,
    location           geometry(Point, 4326)
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_jobs_location ON public.jobs USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_jobs_municipality ON public.jobs (municipality);
CREATE INDEX IF NOT EXISTS idx_jobs_region ON public.jobs (region);
CREATE INDEX IF NOT EXISTS idx_jobs_occupation ON public.jobs (occupation);
CREATE INDEX IF NOT EXISTS idx_jobs_published_at ON public.jobs (published_at);
-- Upsert support
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_job_id ON public.jobs (job_id);

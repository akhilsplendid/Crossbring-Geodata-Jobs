-- Spatial analysis examples

-- Jobs within 50km of a given coordinate
-- Replace :lon and :lat with actual values
-- Example: SELECT * FROM nearby_jobs(18.0686, 59.3293, 50000);
DROP FUNCTION IF EXISTS nearby_jobs(double precision, double precision, integer);
CREATE OR REPLACE FUNCTION nearby_jobs(lon double precision, lat double precision, meters integer)
RETURNS TABLE (
  id bigint,
  title text,
  company text,
  city text,
  municipality text,
  region text,
  occupation text,
  distance_m double precision
) AS $$
  SELECT j.id, j.title, j.company, j.city, j.municipality, j.region, j.occupation,
         ST_Distance(j.location::geography, ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) AS distance_m
  FROM public.jobs j
  WHERE j.location IS NOT NULL
    AND ST_DWithin(j.location::geography, ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography, meters)
  ORDER BY distance_m ASC
  LIMIT 5000;
$$ LANGUAGE sql STABLE;


-- Job density by municipality
-- Counts jobs and returns centroids for quick map markers
WITH m AS (
  SELECT municipality,
         COUNT(*) AS job_count,
         ST_Centroid(ST_Collect(location)) AS center_geom
  FROM public.jobs
  WHERE location IS NOT NULL
  GROUP BY municipality
)
SELECT municipality, job_count, ST_AsText(center_geom) AS wkt_center
FROM m
ORDER BY job_count DESC
LIMIT 100;


-- Clustering analysis for Data Engineer-related roles (DBSCAN in meters)
-- eps = 10000 meters, minpoints = 5
SELECT id, title, occupation, city,
       ST_ClusterDBSCAN(location, eps := 10000, minpoints := 5) OVER () AS cluster_id
FROM public.jobs
WHERE location IS NOT NULL
  AND (occupation ILIKE '%data engineer%' OR title ILIKE '%data engineer%');


-- Temporal trend: monthly job postings per municipality
SELECT DATE_TRUNC('month', published_at) AS month,
       municipality,
       COUNT(*) AS postings
FROM public.jobs
WHERE published_at IS NOT NULL
GROUP BY month, municipality
ORDER BY month DESC, postings DESC;


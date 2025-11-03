import os
import time
import json
import argparse
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


SEARCH_URL = "https://platsbanken-api.arbetsformedlingen.se/jobs/v1/search"
DETAIL_URL = "https://platsbanken-api.arbetsformedlingen.se/jobs/v1/job/{job_id}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch jobs from Arbetsförmedlingen API and upsert into PostGIS.")
    p.add_argument("--occupation-field", default=None,
                   help="occupationField filter value (e.g., 'apaJ_2ja_LuF'). If set, overrides payload file.")
    p.add_argument("--payload-file", default=None,
                   help="Path to JSON payload file for search POST. If not set, a default payload is built.")
    p.add_argument("--max-records", type=int, default=25, help="maxRecords per request (API default 25).")
    p.add_argument("--pages", type=int, default=5, help="Number of pages to fetch (startIndex increments by maxRecords).")
    p.add_argument("--sleep", type=float, default=0.5, help="Sleep seconds between requests to be polite.")
    p.add_argument("--schema", default="public", help="Target schema")
    p.add_argument("--table", default="jobs", help="Target table")
    return p.parse_args()


def get_engine() -> Engine:
    url = os.environ.get("PG_DATABASE_URL")
    if not url:
        raise SystemExit("PG_DATABASE_URL environment variable is required.")
    return create_engine(url)


def build_payload(args: argparse.Namespace, start_index: int) -> Dict[str, Any]:
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        filters = []
        if args.occupation_field:
            filters.append({"type": "occupationField", "value": args.occupation_field})
        payload = {
            "filters": filters,
            "fromDate": None,
            "order": "relevance",
            "maxRecords": args.max_records,
            "startIndex": start_index,
            "toDate": None,
            "source": "pb",
        }
    payload["startIndex"] = start_index
    payload["maxRecords"] = args.max_records
    return payload


def search_page(payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(SEARCH_URL, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_detail(job_id: str) -> Optional[Dict[str, Any]]:
    url = DETAIL_URL.format(job_id=job_id)
    r = requests.get(url, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def upsert_job(engine: Engine, schema: str, table: str, d: Dict[str, Any]) -> None:
    # Map fields from detail response
    job_id = int(d.get("id")) if d.get("id") and str(d.get("id")).isdigit() else None
    title = d.get("title")
    occupation = d.get("occupation")
    company = (d.get("company") or {}).get("name")
    published_at = d.get("publishedDate")
    last_application_at = d.get("lastApplicationDate")
    expiration_at = d.get("expirationDate")

    employment_type = d.get("employmentType")
    work_time_extent = d.get("workTimeExtent")
    duration = d.get("duration")
    positions = d.get("positions")

    wp = d.get("workplace") or {}
    municipality = wp.get("municipality")
    region = wp.get("region")
    city = wp.get("city") or (wp.get("name") if wp.get("unspecifiedWorkplace") else None)
    street_address = wp.get("street")
    postal_code = wp.get("postCode")
    unspecified = bool(wp.get("unspecifiedWorkplace"))
    lon = wp.get("longitude")
    lat = wp.get("latitude")

    # Normalize lon/lat
    try:
        lon_f = float(lon) if lon is not None else None
        lat_f = float(lat) if lat is not None else None
        if lon_f is not None and (lon_f < -180 or lon_f > 180):
            lon_f = None
        if lat_f is not None and (lat_f < -90 or lat_f > 90):
            lat_f = None
    except ValueError:
        lon_f = lat_f = None

    sql = text(f"""
        INSERT INTO {schema}."{table}" (
            job_id, title, company, occupation,
            employment_type, work_time_extent, duration, positions, unspecified_workplace,
            municipality, region, city, street_address, postal_code,
            published_at, last_application_at, expiration_at,
            lon, lat, location
        )
        VALUES (
            :job_id, :title, :company, :occupation,
            :employment_type, :work_time_extent, :duration, :positions, :unspecified_workplace,
            :municipality, :region, :city, :street_address, :postal_code,
            :published_at, :last_application_at, :expiration_at,
            :lon, :lat,
            CASE WHEN :lon IS NOT NULL AND :lat IS NOT NULL
                 THEN ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
                 ELSE NULL END
        )
        ON CONFLICT (job_id) DO UPDATE SET
            title = EXCLUDED.title,
            company = EXCLUDED.company,
            occupation = EXCLUDED.occupation,
            employment_type = EXCLUDED.employment_type,
            work_time_extent = EXCLUDED.work_time_extent,
            duration = EXCLUDED.duration,
            positions = EXCLUDED.positions,
            unspecified_workplace = EXCLUDED.unspecified_workplace,
            municipality = EXCLUDED.municipality,
            region = EXCLUDED.region,
            city = EXCLUDED.city,
            street_address = EXCLUDED.street_address,
            postal_code = EXCLUDED.postal_code,
            published_at = EXCLUDED.published_at,
            last_application_at = EXCLUDED.last_application_at,
            expiration_at = EXCLUDED.expiration_at,
            lon = EXCLUDED.lon,
            lat = EXCLUDED.lat,
            location = EXCLUDED.location
    """)

    with engine.begin() as conn:
        conn.execute(sql, {
            "job_id": job_id,
            "title": title,
            "company": company,
            "occupation": occupation,
            "employment_type": employment_type,
            "work_time_extent": work_time_extent,
            "duration": duration,
            "positions": positions,
            "unspecified_workplace": unspecified,
            "municipality": municipality,
            "region": region,
            "city": city,
            "street_address": street_address,
            "postal_code": postal_code,
            "published_at": published_at,
            "last_application_at": last_application_at,
            "expiration_at": expiration_at,
            "lon": lon_f,
            "lat": lat_f,
        })


def main():
    args = parse_args()
    engine = get_engine()

    total_inserted = 0
    start = 0
    for page in range(args.pages):
        payload = build_payload(args, start)
        res = search_page(payload)
        ads: List[Dict[str, Any]] = res.get("ads", [])
        if not ads:
            break

        for ad in ads:
            job_id = str(ad.get("id"))
            try:
                detail = fetch_detail(job_id)
                if not detail:
                    continue
                upsert_job(engine, args.schema, args.table, detail)
                total_inserted += 1
            except Exception as e:
                # Log and continue
                print(f"Failed job {job_id}: {e}")
            time.sleep(args.sleep)

        start += args.max_records
        time.sleep(args.sleep)

    print(f"Upserted {total_inserted} jobs into {args.schema}.{args.table}.")


if __name__ == "__main__":
    main()


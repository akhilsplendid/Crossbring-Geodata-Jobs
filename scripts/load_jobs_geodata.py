import os
import argparse
import sys

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import geopandas as gpd
from shapely.geometry import Point


CSV_LON = "workplace_longitude"
CSV_LAT = "workplace_latitude"


def parse_args():
    p = argparse.ArgumentParser(description="Load Swedish job CSV into PostGIS with spatial geometry.")
    p.add_argument("--csv", required=True, help="Path to job_details_rows.csv")
    p.add_argument("--table", default="jobs", help="Target table name (default: jobs)")
    p.add_argument("--schema", default="public", help="Target schema (default: public)")
    p.add_argument("--if-exists", choices=["append", "replace"], default="replace",
                   help="Write mode for table (default: replace)")
    p.add_argument("--sample", type=int, default=None, help="Load only first N rows for quick testing")
    return p.parse_args()


def get_engine() -> Engine:
    url = os.environ.get("PG_DATABASE_URL")
    if not url:
        print("Environment variable PG_DATABASE_URL not set. Example: postgresql+psycopg2://user:pass@localhost:5432/jobsdb",
              file=sys.stderr)
        sys.exit(1)
    return create_engine(url)


def ensure_db_objects(engine: Engine, schema: str, table: str):
    ddl = f"""
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE TABLE IF NOT EXISTS {schema}."{table}" (
        id BIGSERIAL PRIMARY KEY,
        source_id BIGINT,
        job_id BIGINT,
        title TEXT,
        company TEXT,
        occupation TEXT,
        employment_type TEXT,
        municipality TEXT,
        region TEXT,
        city TEXT,
        street_address TEXT,
        postal_code TEXT,
        published_at TIMESTAMP NULL,
        last_application_at TIMESTAMP NULL,
        expiration_at TIMESTAMP NULL,
        lon DOUBLE PRECISION,
        lat DOUBLE PRECISION,
        location geometry(Point,4326)
    );
    CREATE INDEX IF NOT EXISTS idx_{table}_location ON {schema}."{table}" USING GIST (location);
    CREATE INDEX IF NOT EXISTS idx_{table}_municipality ON {schema}."{table}" (municipality);
    CREATE INDEX IF NOT EXISTS idx_{table}_occupation ON {schema}."{table}" (occupation);
    CREATE INDEX IF NOT EXISTS idx_{table}_published ON {schema}."{table}" (published_at);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


def coerce_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def load_dataframe(csv_path: str, sample: int | None) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)
    if sample:
        df = df.head(sample)

    # Primary filters and type coercions
    for c in [CSV_LON, CSV_LAT]:
        if c not in df.columns:
            raise ValueError(f"Missing required column in CSV: {c}")
    df[CSV_LON] = pd.to_numeric(df[CSV_LON], errors="coerce")
    df[CSV_LAT] = pd.to_numeric(df[CSV_LAT], errors="coerce")

    # Drop invalid coords
    before = len(df)
    df = df.dropna(subset=[CSV_LON, CSV_LAT])
    df = df[(df[CSV_LON] >= -180) & (df[CSV_LON] <= 180) & (df[CSV_LAT] >= -90) & (df[CSV_LAT] <= 90)]
    dropped = before - len(df)

    # Deduplicate on job_id if present
    if "job_id" in df.columns:
        df = df.sort_values(by=["published_date"], ascending=True)
        df = df.drop_duplicates(subset=["job_id"], keep="last")

    print(f"Rows read: {before:,}. Dropped invalid/missing coords: {dropped:,}. To load: {len(df):,}.")
    return df


def transform_to_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    geometry = [Point(xy) for xy in zip(df[CSV_LON], df[CSV_LAT])]
    gdf = gpd.GeoDataFrame(df.copy(), geometry=geometry, crs="EPSG:4326")
    return gdf


def select_and_rename(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    # Map CSV columns to target schema names if available
    mapping = {
        "id": "source_id",
        "job_id": "job_id",
        "title": "title",
        "company_name": "company",
        "occupation": "occupation",
        "employment_type": "employment_type",
        "workplace_municipality": "municipality",
        "workplace_region": "region",
        "workplace_city": "city",
        "workplace_street": "street_address",
        "workplace_post_code": "postal_code",
        "published_date": "published_at",
        "last_application_date": "last_application_at",
        "expiration_date": "expiration_at",
        CSV_LON: "lon",
        CSV_LAT: "lat",
    }
    present = {k: v for k, v in mapping.items() if k in gdf.columns}
    gdf2 = gdf.copy()
    gdf2 = gdf2.rename(columns=present)

    # Coerce datetime columns if present
    for c in ["published_at", "last_application_at", "expiration_at"]:
        if c in gdf2.columns:
            gdf2[c] = coerce_dt(gdf2[c])

    # Only keep selected columns plus geometry
    keep = [
        "source_id", "job_id", "title", "company", "occupation", "employment_type",
        "municipality", "region", "city", "street_address", "postal_code",
        "published_at", "last_application_at", "expiration_at", "lon", "lat", "geometry"
    ]
    keep_existing = [c for c in keep if c in gdf2.columns]
    return gdf2[keep_existing + ["geometry"]].copy()


def write_to_postgis(gdf: gpd.GeoDataFrame, engine: Engine, schema: str, table: str, if_exists: str):
    # Ensure table & indexes exist (idempotent)
    ensure_db_objects(engine, schema, table)

    # GeoPandas writes geometry to a column named 'geom' by default if geometry column is 'geometry'.
    # We want column name 'location'. We'll rename just for the write, then adjust.
    gdf_to_write = gdf.rename_geometry("location")

    # Write
    gdf_to_write.to_postgis(name=table, con=engine, schema=schema, if_exists=if_exists, index=False)

    print(f"Wrote {len(gdf)} rows to {schema}.{table}.")


def main():
    args = parse_args()
    engine = get_engine()

    df = load_dataframe(args.csv, args.sample)
    gdf = transform_to_gdf(df)
    gdf = select_and_rename(gdf)

    write_to_postgis(gdf, engine, args.schema, args.table, args.if_exists)

    # Post-load: ensure spatial index exists (safe if already created)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{args.table}_location ON {args.schema}.\"{args.table}\" USING GIST (location);"))

    print("Done.")


if __name__ == "__main__":
    main()

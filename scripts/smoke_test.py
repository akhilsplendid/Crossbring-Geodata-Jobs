import os
from sqlalchemy import create_engine, text


def main():
    url = os.environ.get("PG_DATABASE_URL")
    if not url:
        raise SystemExit("PG_DATABASE_URL is not set.")
    eng = create_engine(url)

    with eng.begin() as conn:
        # PostGIS check
        v = conn.execute(text("SELECT postgis_full_version();")).scalar()
        print(f"PostGIS: {v.split(',')[0] if v else 'unknown'}")

        total = conn.execute(text("SELECT COUNT(*) FROM public.jobs;"))
        total = total.scalar() or 0
        with_geom = conn.execute(text("SELECT COUNT(*) FROM public.jobs WHERE location IS NOT NULL;"))
        with_geom = with_geom.scalar() or 0
        print(f"Jobs total: {total}, with geometry: {with_geom}")

        # Try nearby function if loaded
        try:
            rows = list(conn.execute(text("SELECT id, title, distance_m FROM nearby_jobs(:lon,:lat,:m) LIMIT 3;"),
                                     {"lon": 18.0686, "lat": 59.3293, "m": 50000}))
            if rows:
                print("Nearby sample:")
                for r in rows:
                    print(f" - {r.title[:60]}... ({int(r.distance_m)} m)")
            else:
                print("Nearby function returned 0 rows (check data around Stockholm).")
        except Exception:
            print("nearby_jobs() not available. Run analytics SQL: make analytics-sql")


if __name__ == "__main__":
    main()


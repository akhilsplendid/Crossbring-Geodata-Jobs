import os
import argparse
import folium
from folium.plugins import MarkerCluster
from sqlalchemy import create_engine, text


def parse_args():
    p = argparse.ArgumentParser(description="Generate a simple folium map from jobs table.")
    p.add_argument("--table", default="jobs", help="Table name (default: jobs)")
    p.add_argument("--schema", default="public", help="Schema (default: public)")
    p.add_argument("--limit", type=int, default=1000, help="Max points to plot (default: 1000)")
    p.add_argument("--out", default="map.html", help="Output HTML path")
    return p.parse_args()


def main():
    args = parse_args()
    url = os.environ.get("PG_DATABASE_URL")
    if not url:
        raise SystemExit("PG_DATABASE_URL is not set.")
    engine = create_engine(url)

    sql = text(f"""
        SELECT title, company, city, municipality, region, ST_Y(location) AS lat, ST_X(location) AS lon
        FROM {args.schema}."{args.table}"
        WHERE location IS NOT NULL
        ORDER BY published_at DESC NULLS LAST
        LIMIT :limit
    """)

    rows = []
    with engine.begin() as conn:
        for r in conn.execute(sql, {"limit": args.limit}):
            rows.append(dict(r._mapping))

    # Default center: Sweden approx (Stockholm)
    m = folium.Map(location=[59.3293, 18.0686], zoom_start=5)
    mc = MarkerCluster().add_to(m)

    for r in rows:
        lat, lon = float(r["lat"]), float(r["lon"])
        popup = f"{r['title']}<br/>{r.get('company','')}<br/>{r.get('city','')}, {r.get('municipality','')}"
        folium.Marker([lat, lon], popup=popup).add_to(mc)

    m.save(args.out)
    print(f"Wrote {args.out} with {len(rows)} markers.")


if __name__ == "__main__":
    main()


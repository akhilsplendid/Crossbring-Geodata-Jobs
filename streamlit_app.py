import os
import math
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


@st.cache_resource(show_spinner=False)
def get_engine():
    url = os.environ.get("PG_DATABASE_URL")
    if not url:
        st.stop()
    return create_engine(url, pool_pre_ping=True)


def load_kpis(engine):
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM public.jobs")).scalar() or 0
        with_geom = conn.execute(text("SELECT COUNT(*) FROM public.jobs WHERE location IS NOT NULL")).scalar() or 0
    return total, with_geom


def load_municipalities(engine):
    sql = text(
        """
        SELECT municipality, COUNT(*) AS c
        FROM public.jobs
        WHERE municipality IS NOT NULL AND municipality <> ''
        GROUP BY municipality
        ORDER BY c DESC, municipality ASC
        LIMIT 200
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(sql).fetchall()
    return [r[0] for r in rows]


def query_jobs(engine, keyword, municipalities, lat, lon, radius_km, limit):
    where = ["location IS NOT NULL"]
    params = {"limit": limit}
    if keyword:
        where.append("(title ILIKE :kw OR occupation ILIKE :kw OR company ILIKE :kw)")
        params["kw"] = f"%{keyword}%"
    if municipalities:
        where.append("municipality = ANY(:muns)")
        params["muns"] = municipalities
    if lat is not None and lon is not None and radius_km:
        where.append(
            "ST_DWithin(location::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :meters)"
        )
        params["lat"] = float(lat)
        params["lon"] = float(lon)
        params["meters"] = int(float(radius_km) * 1000)

    where_sql = " AND ".join(where) if where else "TRUE"
    sql = text(
        f"""
        SELECT id, title, company, municipality, region, city,
               ST_Y(location) AS lat, ST_X(location) AS lon,
               published_at
        FROM public.jobs
        WHERE {where_sql}
        ORDER BY published_at DESC NULLS LAST
        LIMIT :limit
        """
    )
    with engine.begin() as conn:
        df = pd.read_sql(sql, conn, params=params)
    return df


def main():
    st.set_page_config(page_title="Crossbring Geodata Jobs", layout="wide")
    st.title("Crossbring Geodata Jobs – Live Dashboard")
    st.caption("PostGIS-backed job geodata explorer")

    engine = get_engine()
    total, with_geom = load_kpis(engine)

    c1, c2, c3 = st.columns(3)
    c1.metric("Jobs (total)", f"{total:,}")
    c2.metric("With Coordinates", f"{with_geom:,}")
    pct = 0 if total == 0 else int(with_geom * 100 / total)
    c3.metric("Geo Coverage", f"{pct}%")

    st.sidebar.header("Filters")
    keyword = st.sidebar.text_input("Keyword (title/company/occupation)")
    municipalities = load_municipalities(engine)
    mun_sel = st.sidebar.multiselect("Municipality", municipalities, max_selections=5)
    st.sidebar.markdown("---")
    st.sidebar.subheader("Distance Filter")
    lat = st.sidebar.number_input("Latitude", value=59.3293, format="%.6f")
    lon = st.sidebar.number_input("Longitude", value=18.0686, format="%.6f")
    radius = st.sidebar.slider("Radius (km)", min_value=0, max_value=200, value=0, step=5)
    limit = st.sidebar.slider("Result limit", min_value=100, max_value=5000, value=1000, step=100)

    if st.sidebar.button("Run Query"):
        df = query_jobs(engine, keyword, mun_sel, lat, lon, radius, limit)
        st.success(f"Fetched {len(df):,} rows")
        if not df.empty:
            # Map and table
            st.map(df[["lat", "lon"]], zoom=6)
            st.dataframe(df)
        else:
            st.info("No results. Adjust filters and try again.")

    st.markdown("---")
    st.caption("Set PG_DATABASE_URL environment variable before running. Example: postgresql+psycopg2://postgres:postgres@localhost:5432/jobsdb")


if __name__ == "__main__":
    main()


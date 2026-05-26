"""
MODALITY-FLOW — TAM GTFS ETL
Loads GTFS static data into Railway PostgreSQL.

Tables:
  - public.dim_tam_stops       (2112 stops)
  - public.dim_tam_routes      (43 routes)
  - public.dim_tam_trips       (19905 trips)
  - public.dim_tam_stop_times  (462707 stop times)
  - public.dim_tam_calendar    (service calendar)

Usage:
    cd ~/Desktop/Velo
    python3 etl_tam_gtfs.py
"""

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
import warnings
warnings.filterwarnings("ignore")

# --- CONFIG -------------------------------------------------------------------
DB_URL   = "postgresql://postgres:PfbeGtHyxglIyRBZppgxBxPtYMQUmoyy@gondola.proxy.rlwy.net:46226/railway"
GTFS_DIR = "/Users/ozlemdechamps/Desktop/Velo/03_transport_TAM/TAM_GTFS/CSV"


# --- HELPERS ------------------------------------------------------------------
def get_pg():
    return psycopg2.connect(DB_URL)


def upload(df, table, cur, conn, conflict_col=None):
    df = df.replace({np.nan: None})
    cols = list(df.columns)
    values = [tuple(row) for row in df.itertuples(index=False, name=None)]

    if conflict_col:
        sql = f"""
            INSERT INTO {table} ({', '.join(cols)})
            VALUES %s
            ON CONFLICT ({conflict_col}) DO UPDATE SET
            {', '.join([f'{c} = EXCLUDED.{c}' for c in cols if c != conflict_col])}
        """
    else:
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s"

    execute_values(cur, sql, values, page_size=1000)
    conn.commit()
    print(f"  {len(df):,} rows → {table}")


# --- 1. STOPS -----------------------------------------------------------------
def load_stops(cur, conn):
    print("Loading stops...")
    df = pd.read_csv(f"{GTFS_DIR}/stops.csv")
    df = df[["stop_id", "stop_name", "stop_lat", "stop_lon", "stop_code"]].copy()
    df["stop_id"] = df["stop_id"].astype(str)
    df["stop_code"] = df["stop_code"].astype(str)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_tam_stops (
            stop_id   VARCHAR PRIMARY KEY,
            stop_name VARCHAR,
            stop_lat  DOUBLE PRECISION,
            stop_lon  DOUBLE PRECISION,
            stop_code VARCHAR
        )
    """)
    cur.execute("TRUNCATE public.dim_tam_stops")
    conn.commit()
    upload(df, "public.dim_tam_stops", cur, conn, "stop_id")


# --- 2. ROUTES ----------------------------------------------------------------
def load_routes(cur, conn):
    print("Loading routes...")
    df = pd.read_csv(f"{GTFS_DIR}/routes.csv")
    df = df[["route_id", "route_short_name", "route_long_name", "route_type", "route_color"]].copy()
    df.columns = ["route_id", "route_name", "route_long_name", "route_type", "route_color"]
    df["route_id"] = df["route_id"].astype(str)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_tam_routes (
            route_id        VARCHAR PRIMARY KEY,
            route_name      VARCHAR,
            route_long_name VARCHAR,
            route_type      INTEGER,
            route_color     VARCHAR
        )
    """)
    cur.execute("TRUNCATE public.dim_tam_routes")
    conn.commit()
    upload(df, "public.dim_tam_routes", cur, conn, "route_id")


# --- 3. TRIPS -----------------------------------------------------------------
def load_trips(cur, conn):
    print("Loading trips...")
    df = pd.read_csv(f"{GTFS_DIR}/trips.csv")
    df = df[["trip_id", "route_id", "service_id", "trip_headsign", "direction_id"]].copy()
    df["trip_id"]   = df["trip_id"].astype(str)
    df["route_id"]  = df["route_id"].astype(str)
    df["service_id"] = df["service_id"].astype(str)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_tam_trips (
            trip_id       VARCHAR PRIMARY KEY,
            route_id      VARCHAR,
            service_id    VARCHAR,
            trip_headsign VARCHAR,
            direction_id  INTEGER
        )
    """)
    cur.execute("TRUNCATE public.dim_tam_trips")
    conn.commit()
    upload(df, "public.dim_tam_trips", cur, conn, "trip_id")


# --- 4. STOP TIMES ------------------------------------------------------------
def load_stop_times(cur, conn):
    print("Loading stop times (462,707 rows — takes ~1 min)...")
    df = pd.read_csv(f"{GTFS_DIR}/stop_times.csv")
    df = df[["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]].copy()
    df["trip_id"] = df["trip_id"].astype(str)
    df["stop_id"] = df["stop_id"].astype(str)

    cur.execute("""
        DROP TABLE IF EXISTS public.dim_tam_stop_times;
        CREATE TABLE public.dim_tam_stop_times (
            trip_id        VARCHAR,
            arrival_time   VARCHAR,
            departure_time VARCHAR,
            stop_id        VARCHAR,
            stop_sequence  INTEGER
        )
    """)
    conn.commit()

    # Index for fast journey lookup
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tam_stop_times_stop_id
        ON public.dim_tam_stop_times (stop_id, departure_time)
    """)
    conn.commit()

    upload(df, "public.dim_tam_stop_times", cur, conn)


# --- 5. CALENDAR --------------------------------------------------------------
def load_calendar(cur, conn):
    print("Loading calendar...")
    df = pd.read_csv(f"{GTFS_DIR}/calendar.csv")
    df["service_id"] = df["service_id"].astype(str)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_tam_calendar (
            service_id VARCHAR PRIMARY KEY,
            monday     INTEGER,
            tuesday    INTEGER,
            wednesday  INTEGER,
            thursday   INTEGER,
            friday     INTEGER,
            saturday   INTEGER,
            sunday     INTEGER,
            start_date VARCHAR,
            end_date   VARCHAR
        )
    """)
    cur.execute("TRUNCATE public.dim_tam_calendar")
    conn.commit()
    upload(df, "public.dim_tam_calendar", cur, conn, "service_id")


# --- 6. JOURNEY VIEW ----------------------------------------------------------
def create_journey_view(cur, conn):
    print("Creating journey helper view...")
    cur.execute("""
        CREATE OR REPLACE VIEW public.v_tam_next_departures AS
        SELECT
            st.stop_id,
            s.stop_name,
            s.stop_lat,
            s.stop_lon,
            st.trip_id,
            st.departure_time,
            st.stop_sequence,
            r.route_name,
            r.route_long_name,
            r.route_type,
            r.route_color,
            t.trip_headsign,
            t.direction_id
        FROM public.dim_tam_stop_times st
        JOIN public.dim_tam_stops  s ON st.stop_id  = s.stop_id
        JOIN public.dim_tam_trips  t ON st.trip_id  = t.trip_id
        JOIN public.dim_tam_routes r ON t.route_id  = r.route_id;
    """)
    conn.commit()
    print("  View created: public.v_tam_next_departures")


# --- MAIN ---------------------------------------------------------------------
if __name__ == "__main__":
    print("TAM GTFS ETL starting...")
    conn = get_pg()
    cur  = conn.cursor()

    load_stops(cur, conn)
    load_routes(cur, conn)
    load_trips(cur, conn)
    load_stop_times(cur, conn)
    load_calendar(cur, conn)
    create_journey_view(cur, conn)

    # Summary
    for table in ["dim_tam_stops", "dim_tam_routes", "dim_tam_trips",
                  "dim_tam_stop_times", "dim_tam_calendar"]:
        cur.execute(f"SELECT COUNT(*) FROM public.{table}")
        print(f"  {table}: {cur.fetchone()[0]:,} rows")

    cur.close()
    conn.close()
    print("TAM GTFS ETL complete.")

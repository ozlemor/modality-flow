"""
╔══════════════════════════════════════════════════════════════════╗
║         MODALITY-FLOW — Migration Script                        ║
║         DuckDB → Railway PostgreSQL                             ║
╠══════════════════════════════════════════════════════════════════╣
║  Migrates all DuckDB tables to Railway PostgreSQL               ║
║                                                                 ║
║  RUN:                                                           ║
║  /usr/local/bin/python3.14 migrate_to_railway.py               ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import duckdb
import psycopg2
import psycopg2.extras
import pandas as pd
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════

DUCKDB_PATH = Path.home() / "Desktop" / "Velo" / "ETL" / "gold" / "modality_flow.duckdb"

# Railway PostgreSQL
PG_CONFIG = {
    "host":     os.environ["PG_HOST"],
    "port":     int(os.environ.get("PG_PORT", 5432)),
    "database": os.environ.get("PG_DB", "railway"),
    "user":     os.environ.get("PG_USER", "postgres"),
    "password": os.environ["PG_PASSWORD"],
}


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def get_pg():
    return psycopg2.connect(**PG_CONFIG)

def get_duck():
    return duckdb.connect(str(DUCKDB_PATH), read_only=True)


# ══════════════════════════════════════════════════════════════════
# CREATE TABLES IN RAILWAY POSTGRESQL
# ══════════════════════════════════════════════════════════════════

def create_tables(cur):
    """Create all tables in Railway PostgreSQL."""

    print("Creating tables...")

    # ── Schemas ────────────────────────────────────────────────────
    cur.execute("CREATE SCHEMA IF NOT EXISTS modality;")

    # ── Dimension tables first (fact tables FK'leri bunlara bağlı) ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_stations (
            station_id   VARCHAR PRIMARY KEY,
            station_code VARCHAR,
            nom          VARCHAR,
            adresse      VARCHAR,
            lat          DOUBLE PRECISION,
            lon          DOUBLE PRECISION,
            capacite     INTEGER,
            type         VARCHAR,
            source       VARCHAR,
            inserted_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_ecocompteurs (
            compteur_id VARCHAR PRIMARY KEY,
            code        VARCHAR,
            intensite   INTEGER,
            lat         DOUBLE PRECISION,
            lon         DOUBLE PRECISION,
            timestamp   TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_qualite_air (
            date            DATE PRIMARY KEY,
            indice_qualite  INTEGER,
            libelle_qualite VARCHAR,
            no2             INTEGER,
            so2             INTEGER,
            o3              INTEGER,
            pm10            INTEGER,
            pm25            INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_meteo (
            date              DATE PRIMARY KEY,
            temperature_max   DOUBLE PRECISION,
            temperature_min   DOUBLE PRECISION,
            precipitation_sum DOUBLE PRECISION,
            wind_speed_max    DOUBLE PRECISION,
            weather_code      INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_tam_stops (
            stop_id   VARCHAR PRIMARY KEY,
            stop_name VARCHAR,
            stop_lat  DOUBLE PRECISION,
            stop_lon  DOUBLE PRECISION,
            stop_code VARCHAR
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_tam_routes (
            route_id    VARCHAR PRIMARY KEY,
            route_name  VARCHAR,
            route_type  INTEGER,
            route_color VARCHAR
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.ref_co2_factors (
            mode         VARCHAR PRIMARY KEY,
            co2_g_per_km INTEGER,
            label        VARCHAR,
            source       VARCHAR
        )
    """)

    # ── Fact / historique tables (FK'ler dim tablolarına bağlı) ────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.fact_velomagg_historique (
            station_id      VARCHAR REFERENCES public.dim_stations(station_id) ON DELETE CASCADE,
            timestamp       TIMESTAMP,
            bisiklet_sayisi INTEGER,
            source          VARCHAR DEFAULT 'ngsi_timeseries'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.fact_parking_historique (
            parking_id      VARCHAR REFERENCES public.dim_stations(station_id) ON DELETE CASCADE,
            timestamp       TIMESTAMP,
            spots_available INTEGER,
            source          VARCHAR DEFAULT 'ngsi_timeseries'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.fact_ecocounter_historique (
            compteur_id VARCHAR REFERENCES public.dim_ecocompteurs(compteur_id) ON DELETE CASCADE,
            timestamp   TIMESTAMP,
            intensite   INTEGER,
            source      VARCHAR DEFAULT 'ngsi_timeseries'
        )
    """)

    # ── Real-time tables (modality schema) ─────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS modality.fact_station_status (
            id              SERIAL PRIMARY KEY,
            station_id      VARCHAR REFERENCES public.dim_stations(station_id) ON DELETE CASCADE,
            bikes_available INTEGER,
            docks_available INTEGER,
            is_renting      BOOLEAN,
            is_returning    BOOLEAN,
            timestamp       TIMESTAMP,
            source          VARCHAR DEFAULT 'gbfs'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS modality.fact_parkings_status (
            id              SERIAL PRIMARY KEY,
            parking_id      VARCHAR REFERENCES public.dim_stations(station_id) ON DELETE CASCADE,
            free_spots      INTEGER,
            total_spots     INTEGER,
            taux_occupation DOUBLE PRECISION,
            status          VARCHAR,
            lat             DOUBLE PRECISION,
            lon             DOUBLE PRECISION,
            timestamp       TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS modality.fact_free_bikes (
            bike_id         VARCHAR PRIMARY KEY,
            lat             DOUBLE PRECISION,
            lon             DOUBLE PRECISION,
            is_reserved     BOOLEAN,
            is_disabled     BOOLEAN,
            vehicle_type_id VARCHAR,
            timestamp       TIMESTAMP
        )
    """)

    # ── Indexes (Android sorgu performansı için) ───────────────────
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_fact_velo_station   ON public.fact_velomagg_historique(station_id)",
        "CREATE INDEX IF NOT EXISTS idx_fact_velo_timestamp ON public.fact_velomagg_historique(timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_fact_velo_sta_ts    ON public.fact_velomagg_historique(station_id, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_fact_park_parking   ON public.fact_parking_historique(parking_id)",
        "CREATE INDEX IF NOT EXISTS idx_fact_eco_compteur   ON public.fact_ecocounter_historique(compteur_id)",
        "CREATE INDEX IF NOT EXISTS idx_status_station      ON modality.fact_station_status(station_id)",
        "CREATE INDEX IF NOT EXISTS idx_status_timestamp    ON modality.fact_station_status(timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_status_sta_ts       ON modality.fact_station_status(station_id, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_parkings_parking    ON modality.fact_parkings_status(parking_id)",
        "CREATE INDEX IF NOT EXISTS idx_stations_type       ON public.dim_stations(type)",
        "CREATE INDEX IF NOT EXISTS idx_stations_lat_lon    ON public.dim_stations(lat, lon)",
        "CREATE INDEX IF NOT EXISTS idx_meteo_date          ON public.dim_meteo(date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_aqi_date            ON public.dim_qualite_air(date DESC)",
    ]
    for idx in indexes:
        cur.execute(idx)

    # ── Views (Android tek sorguyla tüm veriyi alır) ───────────────
    cur.execute("""
        CREATE OR REPLACE VIEW public.v_stations_overview AS
        SELECT
            s.station_id,
            s.nom,
            s.adresse,
            s.lat,
            s.lon,
            s.capacite,
            f.bikes_available,
            f.docks_available,
            f.is_renting,
            f.timestamp AS realtime_ts,
            ROUND(f.bikes_available * 100.0 / NULLIF(s.capacite, 0), 1) AS taux_disponibilite,
            CASE
                WHEN f.bikes_available * 100.0 / NULLIF(s.capacite, 0) >= 50 THEN 'good'
                WHEN f.bikes_available * 100.0 / NULLIF(s.capacite, 0) >= 20 THEN 'average'
                ELSE 'low'
            END AS availability_level,
            m.temperature_max,
            m.temperature_min,
            m.precipitation_sum,
            m.wind_speed_max,
            m.weather_code,
            q.indice_qualite,
            q.libelle_qualite,
            q.no2,
            q.o3,
            q.pm10
        FROM public.dim_stations s
        LEFT JOIN modality.fact_station_status f
            ON s.station_id = f.station_id
            AND f.timestamp = (
                SELECT MAX(timestamp) FROM modality.fact_station_status
                WHERE station_id = s.station_id
            )
        LEFT JOIN public.dim_meteo m ON CURRENT_DATE = m.date
        LEFT JOIN public.dim_qualite_air q ON CURRENT_DATE = q.date
        WHERE s.type = 'velomagg'
        ORDER BY s.nom
    """)

    cur.execute("""
        CREATE OR REPLACE VIEW public.v_parkings_overview AS
        SELECT
            s.station_id,
            s.nom,
            s.adresse,
            s.lat,
            s.lon,
            s.capacite,
            p.free_spots,
            p.total_spots,
            p.taux_occupation,
            p.status,
            p.timestamp AS realtime_ts
        FROM public.dim_stations s
        LEFT JOIN modality.fact_parkings_status p
            ON s.station_id = p.parking_id
            AND p.timestamp = (
                SELECT MAX(timestamp) FROM modality.fact_parkings_status
                WHERE parking_id = s.station_id
            )
        WHERE s.type = 'parking'
        ORDER BY s.nom
    """)

    print("Tables, indexes and views created!")


# ══════════════════════════════════════════════════════════════════
# MIGRATE DATA
# ══════════════════════════════════════════════════════════════════

def migrate_table(duck_con, pg_con, pg_cur, table_name, pg_table=None, chunk_size=5000):
    if pg_table is None:
        pg_table = table_name

    try:
        df = duck_con.execute(f"SELECT * FROM {table_name}").fetchdf()

        if df.empty:
            print(f"   ⚠️  {table_name}: empty, skipping")
            return 0

        df = df.where(pd.notnull(df), None)

        # Use COPY for fast bulk insert
        import io
        output = io.StringIO()
        df.to_csv(output, sep='\t', header=False, index=False, na_rep='\\N')
        output.seek(0)

        cols = df.columns.tolist()
        pg_cur.copy_from(output, pg_table, columns=cols, null='\\N')
        pg_con.commit()

        print(f"   ✅ {table_name} → {pg_table}: {len(df)} rows migrated")
        return len(df)

    except Exception as e:
        print(f"   ❌ {table_name}: {e}")
        pg_con.rollback()
        return 0


# ══════════════════════════════════════════════════════════════════
# MAIN MIGRATION
# ══════════════════════════════════════════════════════════════════

def run():
    start = datetime.now()
    print("Migration DuckDB → Railway PostgreSQL")
    print(f"   DuckDB: {DUCKDB_PATH}")
    print(f"   PostgreSQL: {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}")
    print()

    # Connect
    duck_con = get_duck()
    pg_con   = get_pg()
    pg_cur   = pg_con.cursor()

    # Create tables
    create_tables(pg_cur)
    pg_con.commit()

    # Migrate tables
    print("\nMigrating data...")

    # dimension tables — order matters: dim_ecocompteurs must come before fact_ecocounter_historique (FK)
    dim_tables = [
        "dim_stations",
        "dim_qualite_air",
        "dim_meteo",
        "dim_tam_stops",
        "dim_tam_routes",
        "dim_ecocompteurs",
        "ref_co2_factors",
    ]

    for table in dim_tables:
        migrate_table(duck_con, pg_con, pg_cur, table)

    # Migrate historique (large table — chunked)
    print("\nMigrating historique (644,880 rows — this may take a while)...")
    migrate_table(duck_con, pg_con, pg_cur, "fact_velomagg_historique", chunk_size=5000)
    migrate_table(duck_con, pg_con, pg_cur, "fact_parking_historique", chunk_size=1000)
    migrate_table(duck_con, pg_con, pg_cur, "fact_ecocounter_historique", chunk_size=1000)

    # Report
    all_tables = [
        ("public.dim_stations",              "dim_stations"),
        ("public.dim_qualite_air",           "dim_qualite_air"),
        ("public.dim_meteo",                 "dim_meteo"),
        ("public.dim_tam_stops",             "dim_tam_stops"),
        ("public.dim_tam_routes",            "dim_tam_routes"),
        ("public.dim_ecocompteurs",          "dim_ecocompteurs"),
        ("public.ref_co2_factors",           "ref_co2_factors"),
        ("public.fact_velomagg_historique",  "fact_velomagg_historique"),
        ("public.fact_parking_historique",   "fact_parking_historique"),
        ("public.fact_ecocounter_historique","fact_ecocounter_historique"),
        ("modality.fact_station_status",     None),
        ("modality.fact_parkings_status",    None),
        ("modality.fact_free_bikes",         None),
    ]
    print("\nFinal counts in Railway PostgreSQL:")
    for pg_table, _ in all_tables:
        try:
            pg_cur.execute(f"SELECT COUNT(*) FROM {pg_table}")
            n = pg_cur.fetchone()[0]
            print(f"   {pg_table:<45} {n:>8} rows")
        except Exception as e:
            print(f"   {pg_table:<45} ERROR: {e}")

    pg_cur.close()
    pg_con.close()
    duck_con.close()

    elapsed = (datetime.now() - start).seconds
    print(f"\nMigration completed in {elapsed}s")


if __name__ == "__main__":
    run()
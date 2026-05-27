"""
MODALITY-FLOW — Lille ETL Pipeline
Loads all Lille data into Railway PostgreSQL (lille schema).

Tables:
  - lille.dim_vlille_stations     (V'Lille stations real-time)
  - lille.dim_parkings            (Parking MEL real-time)
  - lille.dim_arrets              (ilévia stops)
  - lille.dim_bike_histo          (bike count history)
  - lille.dim_emprunt_vlille      (V'Lille usage)
  - lille.dim_qualite_air         (AQI Atmo HDF)
  - lille.dim_meteo               (Open-Meteo)
  - lille.dim_abris_velo          (bike shelters)
  - lille.dim_schema_cyclable     (cycling schema 2035)

Usage:
    cd ~/Desktop/Velo
    python3 etl_lille.py
"""

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
import requests
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# --- CONFIG -------------------------------------------------------------------
DB_URL   = "postgresql://postgres:PfbeGtHyxglIyRBZppgxBxPtYMQUmoyy@gondola.proxy.rlwy.net:46226/railway"
LILLE_DIR = "/Users/ozlemdechamps/Desktop/Velo/Lille"

LILLE_LAT = 50.6292
LILLE_LON = 3.0573


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


# --- SCHEMA -------------------------------------------------------------------
def create_schema(cur, conn):
    print("Creating lille schema...")
    cur.execute("CREATE SCHEMA IF NOT EXISTS lille")
    conn.commit()


# --- 1. V'LILLE STATIONS ------------------------------------------------------
def load_vlille(cur, conn):
    print("Loading V'Lille stations...")
    df = pd.read_csv(f"{LILLE_DIR}/vlille_temps_reel.csv")

    cur.execute("""
        DROP TABLE IF EXISTS lille.dim_vlille_stations;
        CREATE TABLE lille.dim_vlille_stations (
            station_id      VARCHAR PRIMARY KEY,
            nom             VARCHAR,
            adresse         VARCHAR,
            commune         VARCHAR,
            code_insee      VARCHAR,
            etat            VARCHAR,
            type            VARCHAR,
            nb_places_dispo INTEGER,
            nb_velos_dispo  INTEGER,
            etat_connexion  VARCHAR,
            lon             DOUBLE PRECISION,
            lat             DOUBLE PRECISION,
            date_modification TIMESTAMP
        )
    """)
    conn.commit()

    out = pd.DataFrame()
    out["station_id"]       = df["identifiant_station"].astype(str)
    out["nom"]              = df["nom"]
    out["adresse"]          = df["adresse"]
    out["commune"]          = df["commune"]
    out["code_insee"]       = df["code_insee"].astype(str)
    out["etat"]             = df["etat"]
    out["type"]             = df["type"]
    out["nb_places_dispo"]  = pd.to_numeric(df["nb_places_dispo"], errors="coerce").fillna(0).astype(int)
    out["nb_velos_dispo"]   = pd.to_numeric(df["nb_velos_dispo"], errors="coerce").fillna(0).astype(int)
    out["etat_connexion"]   = df["etat_connexion"]
    out["lon"]              = pd.to_numeric(df["x"], errors="coerce")
    out["lat"]              = pd.to_numeric(df["y"], errors="coerce")
    out["date_modification"] = pd.to_datetime(df["date_modification"], errors="coerce")

    upload(out, "lille.dim_vlille_stations", cur, conn, "station_id")


# --- 2. PARKINGS --------------------------------------------------------------
def load_parkings(cur, conn):
    print("Loading parkings...")
    df = pd.read_csv(f"{LILLE_DIR}/parking.csv")

    cur.execute("""
        DROP TABLE IF EXISTS lille.dim_parkings;
        CREATE TABLE lille.dim_parkings (
            parking_id  VARCHAR PRIMARY KEY,
            nom         VARCHAR,
            adresse     VARCHAR,
            ville       VARCHAR,
            code_insee  VARCHAR,
            etat        VARCHAR,
            nb_total    INTEGER,
            nb_libre    INTEGER,
            taux_occupation DOUBLE PRECISION,
            lon         DOUBLE PRECISION,
            lat         DOUBLE PRECISION,
            timestamp   TIMESTAMP
        )
    """)
    conn.commit()

    out = pd.DataFrame()
    out["parking_id"]      = df["id"].astype(str)
    out["nom"]             = df["nom"]
    out["adresse"]         = df["adresse"]
    out["ville"]           = df["ville"]
    out["code_insee"]      = df["code_insee"].astype(str)
    out["etat"]            = df["etat"]
    out["nb_total"]        = pd.to_numeric(df["nbr_total"], errors="coerce").fillna(0).astype(int)
    out["nb_libre"]        = pd.to_numeric(df["nbr_libre"], errors="coerce").fillna(0).astype(int)
    out["taux_occupation"] = ((out["nb_total"] - out["nb_libre"]) / out["nb_total"].replace(0, 1) * 100).round(1)
    out["lon"]             = pd.to_numeric(df["longitude"], errors="coerce")
    out["lat"]             = pd.to_numeric(df["latitude"], errors="coerce")
    out["timestamp"]       = pd.to_datetime(df["dtdate"], errors="coerce")

    upload(out, "lille.dim_parkings", cur, conn, "parking_id")


# --- 3. ARRETS ----------------------------------------------------------------
def load_arrets(cur, conn):
    print("Loading ilévia stops...")
    df = pd.read_csv(f"{LILLE_DIR}/arret_point.csv")

    cur.execute("""
        DROP TABLE IF EXISTS lille.dim_arrets;
        CREATE TABLE lille.dim_arrets (
            stop_id     VARCHAR PRIMARY KEY,
            stop_name   VARCHAR,
            stop_desc   VARCHAR,
            commune     VARCHAR,
            lon         DOUBLE PRECISION,
            lat         DOUBLE PRECISION
        )
    """)
    conn.commit()

    out = pd.DataFrame()
    out["stop_id"]   = df["stop_id"].astype(str)
    out["stop_name"] = df["stop_name"]
    out["stop_desc"] = df.get("stop_desc", "")
    out["commune"]   = df.get("commune", "")
    out["lon"]       = pd.to_numeric(df["x"], errors="coerce")
    out["lat"]       = pd.to_numeric(df["y"], errors="coerce")

    upload(out, "lille.dim_arrets", cur, conn, "stop_id")


# --- 4. BIKE HISTORY ----------------------------------------------------------
def load_bike_histo(cur, conn):
    print("Loading bike history...")
    try:
        df = pd.read_csv(f"{LILLE_DIR}/bike_histo.csv")

        cur.execute("""
            DROP TABLE IF EXISTS lille.dim_bike_histo;
            CREATE TABLE lille.dim_bike_histo (
                id          SERIAL PRIMARY KEY,
                compteur_id VARCHAR,
                nom         VARCHAR,
                adresse     VARCHAR,
                ville       VARCHAR,
                code_insee  VARCHAR,
                annee       INTEGER,
                semaine     INTEGER,
                mjo         INTEGER,
                lon         DOUBLE PRECISION,
                lat         DOUBLE PRECISION
            )
        """)
        conn.commit()

        out = pd.DataFrame()
        out["compteur_id"] = df["id"].astype(str)
        out["nom"]         = df["nom"]
        out["adresse"]     = df["adresse"]
        out["ville"]       = df["ville"]
        out["code_insee"]  = df["code_insee"].astype(str)
        out["annee"]       = pd.to_numeric(df["annee"], errors="coerce")
        out["semaine"]     = pd.to_numeric(df["semaine"], errors="coerce")
        out["mjo"]         = pd.to_numeric(df["mjo"], errors="coerce")
        out["lon"]         = pd.to_numeric(df["longitude"], errors="coerce")
        out["lat"]         = pd.to_numeric(df["latitude"], errors="coerce")

        upload(out, "lille.dim_bike_histo", cur, conn)

    except Exception as e:
        print(f"  bike_histo error: {e}")


# --- 5. EMPRUNT V'LILLE -------------------------------------------------------
def load_emprunt(cur, conn):
    print("Loading V'Lille usage (3M rows — takes ~2 min)...")
    try:
        df = pd.read_csv(f"{LILLE_DIR}/emprunt.csv")

        cur.execute("""
            DROP TABLE IF EXISTS lille.dim_emprunt_vlille;
            CREATE TABLE lille.dim_emprunt_vlille (
                id_emprunt          VARCHAR PRIMARY KEY,
                jour_emprunt        VARCHAR,
                date_debut          TIMESTAMP,
                date_arrivee        TIMESTAMP,
                id_station_depart   VARCHAR,
                nom_station_depart  VARCHAR,
                id_station_arrivee  VARCHAR,
                nom_station_arrivee VARCHAR,
                code_insee_depart   VARCHAR,
                commune_depart      VARCHAR,
                code_insee_arrivee  VARCHAR,
                commune_arrivee     VARCHAR
            )
        """)
        conn.commit()

        out = pd.DataFrame()
        out["id_emprunt"]          = df["id_emprunt"].astype(str)
        out["jour_emprunt"]        = df["jour_emprunt"]
        out["date_debut"]          = pd.to_datetime(df["date_heure_debut"], errors="coerce")
        out["date_arrivee"]        = pd.to_datetime(df["date_heure_arrivee"], errors="coerce")
        out["id_station_depart"]   = df["id_station_depart"].astype(str)
        out["nom_station_depart"]  = df["nom_station_depart"]
        out["id_station_arrivee"]  = df["id_station_arrivee"].astype(str)
        out["nom_station_arrivee"] = df["nom_station_arrivee"]
        out["code_insee_depart"]   = df["code_insee_depart"].astype(str)
        out["commune_depart"]      = df["commune_depart"]
        out["code_insee_arrivee"]  = df["code_insee_arrivee"].astype(str)
        out["commune_arrivee"]     = df["commune_arrivee"]

        # Insert in chunks to avoid SSL timeout
        chunk_size = 50000
        total = 0
        for i in range(0, len(out), chunk_size):
            chunk = out.iloc[i:i+chunk_size]
            conn2 = get_pg()
            cur2 = conn2.cursor()
            values = [tuple(row) for row in chunk.replace({np.nan: None}).itertuples(index=False, name=None)]
            execute_values(cur2, """
                INSERT INTO lille.dim_emprunt_vlille VALUES %s
                ON CONFLICT (id_emprunt) DO NOTHING
            """, values, page_size=1000)
            conn2.commit()
            cur2.close(); conn2.close()
            total += len(chunk)
            print(f"  {total:,} / {len(out):,} rows inserted...")

        print(f"  Total: {total:,} rows → lille.dim_emprunt_vlille")

    except Exception as e:
        print(f"  emprunt error: {e}")


# --- 6. AQI -------------------------------------------------------------------
def load_aqi(cur, conn):
    print("Loading AQI (Atmo HDF)...")
    df = pd.read_csv(f"{LILLE_DIR}/ind_hdf_2021_-7040852117194928177.csv")

    # Filter Lille communes (59xxx)
    df_lille = df[df["code_zone"].astype(str).str.startswith("59")].copy()
    print(f"  Lille communes: {len(df_lille)}")

    cur.execute("""
        DROP TABLE IF EXISTS lille.dim_qualite_air;
        CREATE TABLE lille.dim_qualite_air (
            id          SERIAL PRIMARY KEY,
            date_ech    DATE,
            code_qual   INTEGER,
            lib_qual    VARCHAR,
            code_zone   VARCHAR,
            lib_zone    VARCHAR,
            code_no2    INTEGER,
            code_o3     INTEGER,
            code_pm10   INTEGER,
            code_pm25   INTEGER,
            lon         DOUBLE PRECISION,
            lat         DOUBLE PRECISION
        )
    """)
    conn.commit()

    out = pd.DataFrame()
    out["date_ech"]  = pd.to_datetime(df_lille["date_ech"], errors="coerce").dt.date
    out["code_qual"] = pd.to_numeric(df_lille["code_qual"], errors="coerce")
    out["lib_qual"]  = df_lille["lib_qual"]
    out["code_zone"] = df_lille["code_zone"].astype(str)
    out["lib_zone"]  = df_lille["lib_zone"]
    out["code_no2"]  = pd.to_numeric(df_lille["code_no2"], errors="coerce")
    out["code_o3"]   = pd.to_numeric(df_lille["code_o3"], errors="coerce")
    out["code_pm10"] = pd.to_numeric(df_lille["code_pm10"], errors="coerce")
    out["code_pm25"] = pd.to_numeric(df_lille["code_pm25"], errors="coerce")
    out["lon"]       = pd.to_numeric(df_lille["x_wgs84"], errors="coerce")
    out["lat"]       = pd.to_numeric(df_lille["y_wgs84"], errors="coerce")

    upload(out, "lille.dim_qualite_air", cur, conn)


# --- 7. METEO -----------------------------------------------------------------
def load_meteo(cur, conn):
    print("Loading meteo (Open-Meteo Lille)...")

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LILLE_LAT}&longitude={LILLE_LON}"
        f"&current=temperature_2m,precipitation,wind_speed_10m,weather_code"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
        f"&timezone=Europe/Paris&forecast_days=7"
    )
    data = requests.get(url, timeout=15).json()

    cur.execute("""
        DROP TABLE IF EXISTS lille.dim_meteo;
        CREATE TABLE lille.dim_meteo (
            date              DATE PRIMARY KEY,
            temperature_max   DOUBLE PRECISION,
            temperature_min   DOUBLE PRECISION,
            precipitation_sum DOUBLE PRECISION,
            wind_speed_max    DOUBLE PRECISION,
            weather_code      INTEGER
        )
    """)
    conn.commit()

    daily = data.get("daily", {})
    rows = []
    for i, date in enumerate(daily.get("time", [])):
        rows.append((
            date,
            daily["temperature_2m_max"][i],
            daily["temperature_2m_min"][i],
            daily["precipitation_sum"][i],
            daily["wind_speed_10m_max"][i],
            daily["weather_code"][i],
        ))

    execute_values(cur, """
        INSERT INTO lille.dim_meteo (date, temperature_max, temperature_min, precipitation_sum, wind_speed_max, weather_code)
        VALUES %s ON CONFLICT (date) DO UPDATE SET
            temperature_max = EXCLUDED.temperature_max,
            precipitation_sum = EXCLUDED.precipitation_sum
    """, rows)
    conn.commit()
    print(f"  {len(rows)} days → lille.dim_meteo")


# --- 8. ABRIS VELO ------------------------------------------------------------
def load_abris(cur, conn):
    print("Loading bike shelters...")
    try:
        df = pd.read_csv(f"{LILLE_DIR}/abri_velo.csv")
        cur.execute("""
            DROP TABLE IF EXISTS lille.dim_abris_velo;
            CREATE TABLE lille.dim_abris_velo (
                id   SERIAL PRIMARY KEY,
                raw  JSONB
            )
        """)
        conn.commit()
        from psycopg2.extras import Json
        rows = [(Json(row),) for row in df.to_dict(orient="records")]
        cur.executemany("INSERT INTO lille.dim_abris_velo (raw) VALUES (%s)", rows)
        conn.commit()
        print(f"  {len(rows)} rows → lille.dim_abris_velo")
    except Exception as e:
        print(f"  abris skipped: {e}")


# --- 9. DEMOGRAPHICS ----------------------------------------------------------
def load_demographics(cur, conn):
    print("Loading demographics (INSEE Lille communes)...")

    CSV_PATH = "/Users/ozlemdechamps/Desktop/Velo/base-cc-evol-struct-pop-2020_csv/base-cc-evol-struct-pop-2020.CSV"

    # Lille Metropole Europeenne de Lille (MEL) communes — 59xxx
    MEL_CODES = [
        '59009','59013','59024','59028','59030','59043','59047','59052',
        '59056','59065','59098','59100','59106','59113','59119','59122',
        '59130','59148','59150','59152','59163','59168','59175','59183',
        '59193','59194','59196','59202','59220','59227','59246','59247',
        '59256','59272','59278','59279','59281','59298','59299','59303',
        '59328','59335','59339','59343','59346','59350','59360','59368',
        '59378','59386','59388','59391','59399','59402','59410','59411',
        '59420','59426','59436','59441','59450','59458','59463','59470',
        '59477','59482','59483','59484','59507','59508','59509','59512',
        '59527','59543','59553','59560','59563','59566','59572','59578',
        '59599','59606','59607','59609','59611','59616','59625','59635',
        '59636','59644','59646','59648','59649','59650','59654','59656',
        '59658','59660','59662','59663','59670'
    ]

    try:
        df = pd.read_csv(CSV_PATH, sep=';', dtype={'CODGEO': str})
        df_mel = df[df['CODGEO'].isin(MEL_CODES)].copy()
        print(f"  MEL communes found: {len(df_mel)}")

        pop   = df_mel['P20_POP'].replace(0, np.nan)
        pop15 = df_mel['C20_POP15P'].replace(0, np.nan)

        out = pd.DataFrame()
        out['codgeo']          = df_mel['CODGEO'].values
        out['population']      = df_mel['P20_POP'].values
        out['pct_young_adult'] = (df_mel['P20_POP1529'] / pop * 100).round(2).values
        out['pct_active']      = ((df_mel['P20_POP3044'] + df_mel['P20_POP4559']) / pop * 100).round(2).values
        out['pct_65plus']      = ((df_mel['P20_POP6074'] + df_mel['P20_POP7589'] + df_mel['P20_POP90P']) / pop * 100).round(2).values
        out['pct_cadres']      = (df_mel['C20_POP15P_CS3'] / pop15 * 100).round(2).values
        out['pct_employes']    = (df_mel['C20_POP15P_CS5'] / pop15 * 100).round(2).values
        out['pct_ouvriers']    = (df_mel['C20_POP15P_CS6'] / pop15 * 100).round(2).values
        out['pct_high_income'] = out['pct_cadres']
        out['pct_low_income']  = out['pct_employes'] + out['pct_ouvriers']

        cur.execute("""
            DROP TABLE IF EXISTS lille.dim_demographics;
            CREATE TABLE lille.dim_demographics (
                codgeo          VARCHAR PRIMARY KEY,
                population      FLOAT,
                pct_young_adult FLOAT,
                pct_active      FLOAT,
                pct_65plus      FLOAT,
                pct_cadres      FLOAT,
                pct_employes    FLOAT,
                pct_ouvriers    FLOAT,
                pct_high_income FLOAT,
                pct_low_income  FLOAT
            )
        """)
        conn.commit()
        upload(out, "lille.dim_demographics", cur, conn, "codgeo")

    except Exception as e:
        print(f"  demographics skipped: {e}")


# --- MAIN ---------------------------------------------------------------------
if __name__ == "__main__":
    print("MODALITY-FLOW — Lille ETL starting...")

    # Her fonksiyon kendi connection'ını açar
    conn = get_pg(); cur = conn.cursor()
    create_schema(cur, conn)
    cur.close(); conn.close()

    conn = get_pg(); cur = conn.cursor()
    load_vlille(cur, conn)
    cur.close(); conn.close()

    conn = get_pg(); cur = conn.cursor()
    load_parkings(cur, conn)
    cur.close(); conn.close()

    conn = get_pg(); cur = conn.cursor()
    load_arrets(cur, conn)
    cur.close(); conn.close()

    conn = get_pg(); cur = conn.cursor()
    load_bike_histo(cur, conn)
    cur.close(); conn.close()

    conn = get_pg(); cur = conn.cursor()
    load_emprunt(cur, conn)
    cur.close(); conn.close()

    conn = get_pg(); cur = conn.cursor()
    load_aqi(cur, conn)
    cur.close(); conn.close()

    conn = get_pg(); cur = conn.cursor()
    load_meteo(cur, conn)
    cur.close(); conn.close()

    conn = get_pg(); cur = conn.cursor()
    load_abris(cur, conn)
    cur.close(); conn.close()

    conn = get_pg(); cur = conn.cursor()
    load_demographics(cur, conn)
    cur.close(); conn.close()

    print("\nLille ETL complete!")

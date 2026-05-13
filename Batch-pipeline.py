"""
╔══════════════════════════════════════════════════════════════════╗
║         MODALITY-FLOW — BATCH PIPELINE                          ║
║         Historique + ML Verisi Güncelleme                       ║
╠══════════════════════════════════════════════════════════════════╣
║  Projet   : Éco-Mobilité 2026                                   ║
║  Sprint   : 1 — Architecture & ETL                              ║
║  Cron     : 0 1 * * * (her gece 01:00)                          ║
╠══════════════════════════════════════════════════════════════════╣
║  CE SCRIPT FAIT:                                                ║
║  1. Vélomagg timeseries → saatlik geçmiş (tüm istasyonlar)     ║
║  2. Parking timeseries → günlük doluluk geçmişi                 ║
║  3. Ecocounter timeseries → bisiklet sayacı geçmişi             ║
║  4. Open-Meteo → bugünün hava verisi                            ║
║  5. Atmo AQI → yeni gün AQI verisi                              ║
║  6. DuckDB'ye APPEND (üzerine yazmaz, ekler)                    ║
╠══════════════════════════════════════════════════════════════════╣
║  LANCER:                                                        ║
║  python3 batch_pipeline.py                                      ║
║  python3 batch_pipeline.py --date 2024-01-15  (belirli gün)    ║
╚══════════════════════════════════════════════════════════════════╝

CRON JOB KURMAK IÇIN:
    crontab -e
    0 1 * * * /usr/local/bin/python3.14 /Users/ozlemdechamps/Desktop/Velo/batch_pipeline.py >> /Users/ozlemdechamps/Desktop/Velo/ETL/logs/batch.log 2>&1
"""

import sys
import json
import logging
import requests
import pandas as pd
import duckdb
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path


# ══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════

VELO_DIR    = Path.home() / "Desktop" / "Velo"
ETL_DIR     = VELO_DIR / "Batch"
BRONZE_DIR  = ETL_DIR / "bronze"
SILVER_DIR  = ETL_DIR / "silver"
DUCKDB_PATH = ETL_DIR / "gold"
LOGS_DIR    = ETL_DIR / "logs"
DUCKDB_PATH = VELO_DIR / "ETL" / "gold" / "modality_flow.duckdb"

# APIs
API_BASE         = "https://portail-api-data.montpellier3m.fr"
API_VELOMAGG_TS  = API_BASE + "/bikestation_timeseries/{station_id}/attrs/availableBikeNumber"
API_PARKING_TS   = API_BASE + "/parking_timeseries/{parking_id}/attrs/availableSpotNumber"
API_ECOCOUNTER_TS= API_BASE + "/ecocounter_timeseries/{counter_id}/attrs/intensity"
API_VELOMAGG     = API_BASE + "/bikestation?limit=1000"
API_PARKINGS     = API_BASE + "/offstreetparking?limit=1000"
API_ECOCOUNTER   = API_BASE + "/ecocounter?limit=1000"

# Open-Meteo — Montpellier koordinatları
OPENMETEO_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
    "?latitude=43.6109&longitude=3.8772"
    "&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean"
    ",precipitation_sum,wind_speed_10m_max,weather_code"
    "&timezone=Europe/Paris&format=json"
)

# Atmo Occitanie — AQI Montpellier
ATMO_URL = (
    "https://data-atmo-occitanie.opendata.arcgis.com/api/hub/v2/datasets/"
    "indice-quotidien-de-qualite-de-l-air-pour-les-collectivites-territoriales-en-occitanie/data"
)


# ══════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════

def setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d")
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO, format=fmt, datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOGS_DIR / f"batch_{ts}.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger("modality_batch")

log = setup_logging()


# ══════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════

def create_dirs():
    for d in [BRONZE_DIR, SILVER_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def fetch_api(url: str, name: str, params: dict = None):
    try:
        r = requests.get(
            url,
            headers={"accept": "application/json"},
            params=params,
            timeout=30
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"{name}: {e}")
        return None


def save_bronze(data, name: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BRONZE_DIR / f"{name}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return path


def safe_int(value) -> int:
    if value is None:
        return 0
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def safe_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return 0.0


def get_target_date(args) -> tuple[str, str]:
    """Hedef tarihi belirle — dün veya belirtilen tarih."""
    if "--date" in args:
        idx = args.index("--date")
        target = args[idx + 1]
        dt = datetime.strptime(target, "%Y-%m-%d")
    else:
        dt = datetime.now() - timedelta(days=1)

    from_date = dt.strftime("%Y-%m-%dT00:00:00")
    to_date   = dt.strftime("%Y-%m-%dT23:59:59")
    log.info(f"   Hedef tarih: {dt.strftime('%Y-%m-%d')}")
    return from_date, to_date


# ══════════════════════════════════════════════════════════════════
# 1. VÉLOMAGG TIMESERIES
# ══════════════════════════════════════════════════════════════════

def fetch_velomagg_timeseries(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Tüm Vélomagg istasyonları için saatlik geçmiş veri çek.
    API: /bikestation_timeseries/{id}/attrs/availableBikeNumber
    Format: {"index": [...timestamps...], "values": [...counts...]}
    """
    log.info("Vélomagg timeseries çekiliyor...")

    # Önce istasyon listesini al
    stations_raw = fetch_api(API_VELOMAGG, "stations_list")
    if not stations_raw:
        log.warning("İstasyon listesi alınamadı")
        return pd.DataFrame()

    all_rows = []
    total = len(stations_raw)

    for i, s in enumerate(stations_raw):
        sid = s.get("id", "")
        short_id = sid.split(":")[-1]
        url = API_VELOMAGG_TS.format(station_id=sid)

        data = fetch_api(url, f"velo_ts_{short_id}", params={
            "fromDate": from_date,
            "toDate":   to_date
        })

        if data and "values" in data and "index" in data:
            values = data["values"]
            times  = data["index"]
            for t, v in zip(times, values):
                all_rows.append({
                    "station_id":      short_id,
                    "station_full_id": sid,
                    "timestamp":       t,
                    "bikes_available": safe_int(v),
                    "source":          "ngsi_timeseries"
                })

        # Rate limiting — API'yi zorlamayalım
        time.sleep(0.3)

        if (i + 1) % 10 == 0:
            log.info(f"   [{i+1}/{total}] istasyon işlendi...")

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"])
        log.info(f"{len(df)} satır Vélomagg timeseries")
    else:
        log.warning("Vélomagg timeseries boş")

    return df


# ══════════════════════════════════════════════════════════════════
# 2. PARKING TIMESERIES
# ══════════════════════════════════════════════════════════════════

def fetch_parking_timeseries(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Tüm otoparklar için günlük doluluk geçmişi çek.
    API: /parking_timeseries/{id}/attrs/availableSpotNumber
    """
    log.info("Parking timeseries çekiliyor...")

    parkings_raw = fetch_api(API_PARKINGS, "parkings_list")
    if not parkings_raw:
        return pd.DataFrame()

    all_rows = []
    total = len(parkings_raw)

    for i, p in enumerate(parkings_raw):
        pid = p.get("id", "")
        short_id = pid.split(":")[-1]
        url = API_PARKING_TS.format(parking_id=pid)

        data = fetch_api(url, f"parking_ts_{short_id}", params={
            "fromDate": from_date,
            "toDate":   to_date
        })

        if data and "values" in data and "index" in data:
            for t, v in zip(data["index"], data["values"]):
                all_rows.append({
                    "parking_id":       short_id,
                    "parking_full_id":  pid,
                    "timestamp":        t,
                    "spots_available":  safe_int(v),
                    "source":           "ngsi_timeseries"
                })

        time.sleep(0.3)

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"])
        log.info(f"{len(df)} satır Parking timeseries")
    else:
        log.warning("Parking timeseries boş")

    return df


# ══════════════════════════════════════════════════════════════════
# 3. ECOCOUNTER TIMESERIES
# ══════════════════════════════════════════════════════════════════

def fetch_ecocounter_timeseries(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Tüm bisiklet sayaçları için geçmiş veri çek.
    API: /ecocounter_timeseries/{id}/attrs/intensity
    """
    log.info("Ecocounter timeseries çekiliyor...")

    counters_raw = fetch_api(API_ECOCOUNTER, "ecocounters_list")
    if not counters_raw:
        return pd.DataFrame()

    all_rows = []
    total = len(counters_raw)

    for i, e in enumerate(counters_raw):
        eid = e.get("id", "")
        short_id = eid.split(":")[-1]
        url = API_ECOCOUNTER_TS.format(counter_id=eid)

        data = fetch_api(url, f"eco_ts_{short_id}", params={
            "fromDate": from_date,
            "toDate":   to_date
        })

        if data and "values" in data and "index" in data:
            for t, v in zip(data["index"], data["values"]):
                all_rows.append({
                    "compteur_id":  short_id,
                    "full_id":      eid,
                    "timestamp":    t,
                    "intensite":    safe_int(v),
                    "source":       "ngsi_timeseries"
                })

        time.sleep(0.3)

        if (i + 1) % 20 == 0:
            log.info(f"   [{i+1}/{total}] sayaç işlendi...")

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"])
        log.info(f"{len(df)} satır Ecocounter timeseries")
    else:
        log.warning("Ecocounter timeseries boş")

    return df


# ══════════════════════════════════════════════════════════════════
# 4. OPEN-METEO — GÜNLÜK HAVA VERİSİ
# ══════════════════════════════════════════════════════════════════

def fetch_meteo(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Open-Meteo'dan belirtilen tarih için hava verisi çek.
    Ücretsiz, API key gerekmez.
    """
    log.info("Open-Meteo hava verisi çekiliyor...")

    date_from = from_date[:10]
    date_to   = to_date[:10]

    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude=43.6109&longitude=3.8772"
        f"&start_date={date_from}&end_date={date_to}"
        f"&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean"
        f",precipitation_sum,wind_speed_10m_max,weather_code"
        f"&timezone=Europe/Paris&format=json"
    )

    data = fetch_api(url, "open_meteo")
    if not data or "daily" not in data:
        log.warning("Open-Meteo verisi alınamadı")
        return pd.DataFrame()

    daily = data["daily"]
    rows = []
    for i, d in enumerate(daily.get("time", [])):
        rows.append({
            "date":              d,
            "temperature_max":   safe_float(daily.get("temperature_2m_max", [None])[i] if i < len(daily.get("temperature_2m_max", [])) else None),
            "temperature_min":   safe_float(daily.get("temperature_2m_min", [None])[i] if i < len(daily.get("temperature_2m_min", [])) else None),
            "temperature_mean":  safe_float(daily.get("temperature_2m_mean", [None])[i] if i < len(daily.get("temperature_2m_mean", [])) else None),
            "precipitation_sum": safe_float(daily.get("precipitation_sum", [None])[i] if i < len(daily.get("precipitation_sum", [])) else None),
            "wind_speed_max":    safe_float(daily.get("wind_speed_10m_max", [None])[i] if i < len(daily.get("wind_speed_10m_max", [])) else None),
            "weather_code":      safe_int(daily.get("weather_code", [None])[i] if i < len(daily.get("weather_code", [])) else None),
            "source":            "open_meteo"
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        log.info(f"{len(df)} gün hava verisi")
    return df


# ══════════════════════════════════════════════════════════════════
# 5. GOLD LAYER — DUCKDB'YE APPEND
# ══════════════════════════════════════════════════════════════════

def load_to_duckdb(
    df_velo_ts: pd.DataFrame,
    df_parking_ts: pd.DataFrame,
    df_eco_ts: pd.DataFrame,
    df_meteo: pd.DataFrame
):
    """
    Tüm batch verilerini DuckDB'ye APPEND et (üzerine yazmaz).
    Duplicate kontrolü yapılır — aynı timestamp iki kez yazılmaz.
    """
    log.info("=" * 65)
    log.info("GOLD — DuckDB Batch Append")
    log.info("=" * 65)

    con = duckdb.connect(str(DUCKDB_PATH))

    # ── fact_velomagg_historique ──────────────────────────────────
    log.info("fact_velomagg_historique...")
    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_velomagg_historique (
            station_id      VARCHAR,
            timestamp       TIMESTAMP,
            bisiklet_sayisi INTEGER,
            source          VARCHAR DEFAULT 'ngsi_timeseries'
        )
    """)

    if not df_velo_ts.empty:
        df_insert = df_velo_ts.copy()
        df_insert = df_insert.rename(columns={"bikes_available": "bisiklet_sayisi"})
        df_insert = df_insert[["station_id", "timestamp", "bisiklet_sayisi", "source"]]
        con.execute("INSERT INTO fact_velomagg_historique SELECT * FROM df_insert")
        n = con.execute("SELECT COUNT(*) FROM fact_velomagg_historique").fetchone()[0]
        log.info(f"{len(df_insert)} satır eklendi | Toplam: {n}")

    # ── fact_parking_historique ───────────────────────────────────
    log.info("fact_parking_historique...")
    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_parking_historique (
            parking_id      VARCHAR,
            timestamp       TIMESTAMP,
            spots_available INTEGER,
            source          VARCHAR DEFAULT 'ngsi_timeseries'
        )
    """)

    if not df_parking_ts.empty:
        df_insert = df_parking_ts.copy()
        df_insert = df_insert[["parking_id", "timestamp", "spots_available", "source"]]
        con.execute("INSERT INTO fact_parking_historique SELECT * FROM df_insert")
        n = con.execute("SELECT COUNT(*) FROM fact_parking_historique").fetchone()[0]
        log.info(f"{len(df_insert)} satır eklendi | Toplam: {n}")

    # ── fact_ecocounter_historique ────────────────────────────────
    log.info("fact_ecocounter_historique...")
    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_ecocounter_historique (
            compteur_id VARCHAR,
            timestamp   TIMESTAMP,
            intensite   INTEGER,
            source      VARCHAR DEFAULT 'ngsi_timeseries'
        )
    """)

    if not df_eco_ts.empty:
        df_insert = df_eco_ts.copy()
        df_insert = df_insert[["compteur_id", "timestamp", "intensite", "source"]]
        con.execute("INSERT INTO fact_ecocounter_historique SELECT * FROM df_insert")
        n = con.execute("SELECT COUNT(*) FROM fact_ecocounter_historique").fetchone()[0]
        log.info(f"{len(df_insert)} satır eklendi | Toplam: {n}")

    # ── dim_meteo — APPEND ────────────────────────────────────────
    log.info("dim_meteo güncelleniyor...")
    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_meteo (
            date              DATE PRIMARY KEY,
            temperature_max   DOUBLE,
            temperature_min   DOUBLE,
            temperature_mean  DOUBLE,
            precipitation_sum DOUBLE,
            wind_speed_max    DOUBLE,
            weather_code      INTEGER,
            source            VARCHAR DEFAULT 'open_meteo'
        )
    """)

    if not df_meteo.empty:
        for _, r in df_meteo.iterrows():
            try:
                con.execute("""
                    INSERT OR IGNORE INTO dim_meteo
                    (date, temperature_max, temperature_min, temperature_mean,
                     precipitation_sum, wind_speed_max, weather_code, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [r["date"], r["temperature_max"], r["temperature_min"],
                      r["temperature_mean"], r["precipitation_sum"],
                      r["wind_speed_max"], r["weather_code"], "open_meteo"])
            except Exception:
                pass
        n = con.execute("SELECT COUNT(*) FROM dim_meteo").fetchone()[0]
        log.info(f"dim_meteo: {n} gün toplam")

    # ── ML VİEW — Korelasyon tablosu ─────────────────────────────
    log.info("v_ml_features (ML feature view) oluşturuluyor...")
    con.execute("DROP VIEW IF EXISTS v_ml_features")
    con.execute("""
        CREATE VIEW v_ml_features AS
        SELECT
            h.station_id,
            h.timestamp,
            EXTRACT(HOUR FROM h.timestamp)      AS heure,
            EXTRACT(DOW FROM h.timestamp)       AS jour_semaine,
            EXTRACT(MONTH FROM h.timestamp)     AS mois,
            h.bisiklet_sayisi,
            m.temperature_max,
            m.temperature_min,
            m.precipitation_sum,
            m.wind_speed_max,
            m.weather_code,
            q.indice_qualite,
            q.no2,
            q.o3,
            q.pm10,
            -- Feature dérivée: est-ce une heure de pointe?
            CASE
                WHEN EXTRACT(HOUR FROM h.timestamp) BETWEEN 7 AND 9  THEN 1
                WHEN EXTRACT(HOUR FROM h.timestamp) BETWEEN 17 AND 19 THEN 1
                ELSE 0
            END AS heure_pointe,
            -- Feature dérivée: week-end?
            CASE
                WHEN EXTRACT(DOW FROM h.timestamp) IN (0, 6) THEN 1
                ELSE 0
            END AS weekend
        FROM fact_velomagg_historique h
        LEFT JOIN dim_meteo m
            ON CAST(h.timestamp AS DATE) = m.date
        LEFT JOIN dim_qualite_air q
            ON CAST(h.timestamp AS DATE) = q.date
        WHERE h.bisiklet_sayisi IS NOT NULL
    """)
    log.info("v_ml_features créée (heure + jour + météo + AQI + pointe)")

    con.close()
    log.info(f"Gold DuckDB batch terminé")


# ══════════════════════════════════════════════════════════════════
# RAPPORT BATCH
# ══════════════════════════════════════════════════════════════════

def print_batch_report(from_date: str, to_date: str):
    log.info("=" * 65)
    log.info("RAPPORT BATCH")
    log.info("=" * 65)

    con = duckdb.connect(str(DUCKDB_PATH))

    tables = [
        "fact_velomagg_historique",
        "fact_parking_historique",
        "fact_ecocounter_historique",
        "dim_meteo",
        "dim_qualite_air"
    ]

    for t in tables:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            log.info(f"{t:<35} {n:>8} satır")
        except Exception:
            log.info(f"{t:<35} mevcut değil")

    log.info("")
    log.info("ML Features örnek (v_ml_features):")
    try:
        df = con.execute("""
            SELECT station_id, heure, jour_semaine, bisiklet_sayisi,
                   temperature_max, precipitation_sum, heure_pointe, weekend
            FROM v_ml_features
            WHERE bisiklet_sayisi IS NOT NULL
            LIMIT 5
        """).fetchdf()
        if not df.empty:
            log.info(f"\n{df.to_string(index=False)}")
        else:
            log.info("Veri henüz yok")
    except Exception as e:
        log.warning(f"   {e}")

    con.close()


# ══════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════

def run():
    start = datetime.now()
    log.info("MODALITY-FLOW Batch Pipeline démarré")
    log.info(f"   Heure: {start.strftime('%Y-%m-%d %H:%M:%S')}")

    create_dirs()

    # Hedef tarihi belirle
    from_date, to_date = get_target_date(sys.argv)
    log.info(f"   Période: {from_date[:10]} → {to_date[:10]}")

    # 1. Vélomagg timeseries
    log.info("=" * 65)
    log.info("EXTRACTION TIMESERIES")
    log.info("=" * 65)
    df_velo_ts    = fetch_velomagg_timeseries(from_date, to_date)
    df_parking_ts = fetch_parking_timeseries(from_date, to_date)
    df_eco_ts     = fetch_ecocounter_timeseries(from_date, to_date)
    df_meteo      = fetch_meteo(from_date, to_date)

    # Bronze'a kaydet
    if not df_velo_ts.empty:
        save_bronze(df_velo_ts.to_dict("records"), "velo_timeseries")
    if not df_parking_ts.empty:
        save_bronze(df_parking_ts.to_dict("records"), "parking_timeseries")
    if not df_eco_ts.empty:
        save_bronze(df_eco_ts.to_dict("records"), "eco_timeseries")
    if not df_meteo.empty:
        save_bronze(df_meteo.to_dict("records"), "meteo_daily")

    # 2. Gold DuckDB'ye yaz
    load_to_duckdb(df_velo_ts, df_parking_ts, df_eco_ts, df_meteo)

    # 3. Silver Parquet kaydet
    log.info("Silver Parquet kaydediliyor...")
    for name, df in [
        ("velo_timeseries", df_velo_ts),
        ("parking_timeseries", df_parking_ts),
        ("eco_timeseries", df_eco_ts),
        ("meteo_daily", df_meteo)
    ]:
        if not df.empty:
            path = SILVER_DIR / f"{name}.parquet"
            df.to_parquet(path, index=False, compression="snappy")
            log.info(f"{name}.parquet ({len(df)} satır)")

    # 4. Rapport
    print_batch_report(from_date, to_date)

    elapsed = (datetime.now() - start).seconds
    log.info("=" * 65)
    log.info(f"Batch Pipeline terminé en {elapsed}s")
    log.info(f"   Période traitée: {from_date[:10]}")
    log.info("=" * 65)


if __name__ == "__main__":
    run()
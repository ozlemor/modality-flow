"""
╔══════════════════════════════════════════════════════════════════╗
║         MODALITY-FLOW — ETL PIPELINE v3                         ║
║         Medallion Architecture: Bronze → Silver → Gold          ║
╠══════════════════════════════════════════════════════════════════╣
║  Projet   : Éco-Mobilité 2026                                   ║
║  Client   : Montpellier Méditerranée Métropole                  ║
║  Sprint   : 1 — Architecture & ETL                              ║
║  Dossier  : ~/Desktop/Velo/ETL/                                 ║
╠══════════════════════════════════════════════════════════════════╣
║  REAL-TIME  → PostgreSQL (fact_station_status, parkings...)     ║
║  HISTORIQUE → DuckDB    (historique, AQI, meteo, TAM...)        ║
╚══════════════════════════════════════════════════════════════════╝

LANCER:
    pip3 install pandas pyarrow duckdb requests psycopg2-binary
    python3 etl_pipeline_v3.py
    python3 etl_pipeline_v3.py --postgres   (avec PostgreSQL)
"""

import os
import sys
import json
import logging
import requests
import pandas as pd
import duckdb
import fcntl
from datetime import datetime, timezone
from pathlib import Path


# ══════════════════════════════════════════════════════════════════
# 0. CONFIGURATION
# ══════════════════════════════════════════════════════════════════

VELO_DIR   = Path.home() / "Desktop" / "Velo"
ETL_DIR    = VELO_DIR / "ETL"
BRONZE_DIR = ETL_DIR / "bronze"
SILVER_DIR = ETL_DIR / "silver"
GOLD_DIR   = ETL_DIR / "gold"
QUALITY_DIR= ETL_DIR / "quality_reports"
LOGS_DIR   = ETL_DIR / "logs"
DUCKDB_PATH= GOLD_DIR / "modality_flow.duckdb"

PG_CONFIG = {
    "host": "localhost", "port": 5432,
    "database": "modality_flow",
    "user": "postgres", "password": "postgres"
}

API_VELOMAGG       = "https://portail-api-data.montpellier3m.fr/bikestation?limit=1000"
API_PARKINGS       = "https://portail-api-data.montpellier3m.fr/offstreetparking?limit=1000"
API_PARKING_SPACES = "https://portail-api-data.montpellier3m.fr/parkingspaces?limit=1000"
API_ECOCOUNTER     = "https://portail-api-data.montpellier3m.fr/ecocounter?limit=1000"
GBFS_BASE          = "https://gbfs.theta.fifteen.eu/gbfs/2.2/montpellier/en"

CSV_SOURCES = {
    "velomagg_historique": VELO_DIR / "01_velomagg"      / "CSV" / "velomagg_historique.csv",
    "qualite_air":         VELO_DIR / "05_environnement"  / "CSV" /"qualite_air_montpellier.csv",
    "meteo":               VELO_DIR / "05_environnement"  / "CSV" /"meteo_montpellier_2024.csv",
    "tam_stops":           VELO_DIR / "03_transport_TAM"  / "TAM_GTFS" / "CSV" / "stops.csv",
    "tam_routes":          VELO_DIR / "03_transport_TAM"  / "TAM_GTFS" / "CSV" / "routes.csv",
    "stationnements_velo": VELO_DIR / "04_mobilite_douce" / "CSV" /"stationnements_cyclables_clean2.csv",
}

CO2_FACTORS = {
    "velo": 0, "tram": 4, "bus": 68, "voiture": 120, "marche": 0
}


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
            logging.FileHandler(LOGS_DIR / f"etl_{ts}.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger("modality_etl")

log = setup_logging()


# ══════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════

def create_dirs():
    for d in [BRONZE_DIR, SILVER_DIR, GOLD_DIR, QUALITY_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    log.info("📁 Structure ETL créée:")
    log.info(f"   Bronze  : {BRONZE_DIR}")
    log.info(f"   Silver  : {SILVER_DIR}")
    log.info(f"   Gold    : {GOLD_DIR}")
    log.info(f"   Quality : {QUALITY_DIR}")
    log.info(f"   Logs    : {LOGS_DIR}")


def fetch_api(url: str, name: str):
    try:
        r = requests.get(url, headers={"accept": "application/json"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        n = len(data) if isinstance(data, list) else "dict"
        log.info(f"{name}: {n} enregistrements")
        return data
    except Exception as e:
        log.warning(f"{name}: {e}")
        return None


def ngsi_val(obj: dict, key: str):
    """Extraire valeur NGSI-LD imbriquée."""
    v = obj.get(key, {})
    if isinstance(v, dict):
        return v.get("value", None)
    return v


def ngsi_coords(obj: dict):
    """Extraire lat/lon d'un objet NGSI-LD."""
    loc = obj.get("location", {})
    if isinstance(loc, dict):
        coords = loc.get("value", {})
        if isinstance(coords, dict):
            c = coords.get("coordinates", [0, 0])
            return float(c[1]) if len(c) > 1 else 0.0, float(c[0]) if len(c) > 0 else 0.0
    return 0.0, 0.0


def ngsi_address(obj: dict) -> str:
    """Extraire adresse d'un objet NGSI-LD."""
    addr = ngsi_val(obj, "address")
    if isinstance(addr, dict):
        return addr.get("streetAddress", "")
    return str(addr) if addr else ""


def safe_int(value) -> int:
    """
    Conversion sécurisée en int.
    Gère les cas: None, '_', '', 'N/A', texte invalide → retourne 0
    """
    if value is None:
        return 0
    s = str(value).strip()
    if s in ("", "_", "N/A", "null", "None", "-"):
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def safe_float(value) -> float:
    """Conversion sécurisée en float."""
    if value is None:
        return 0.0
    s = str(value).strip()
    if s in ("", "_", "N/A", "null", "None", "-"):
        return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def safe_bool(value) -> bool:
    """Conversion sécurisée en bool."""
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in ("true", "1", "yes", "oui")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════
# MESURES DE QUALITÉ
# ══════════════════════════════════════════════════════════════════

def compute_quality(df: pd.DataFrame, name: str) -> dict:
    """
    4 mesures de qualité:
    1. Complétude   → % valeurs non-nulles par colonne
    2. Unicité      → % lignes non dupliquées
    3. Validité géo → coordonnées dans zone Hérault
    4. Fraîcheur    → timestamp d'extraction
    Score global = complétude×0.4 + unicité×0.3 + geo×0.3
    """
    report = {
        "dataset": name,
        "timestamp": now_iso(),
        "nb_lignes": len(df),
        "nb_colonnes": len(df.columns),
        "mesures": {}
    }

    # 1. Complétude
    completeness = {}
    for col in df.columns:
        non_null = df[col].notna().sum()
        pct = round(non_null / max(len(df), 1) * 100, 1)
        completeness[col] = {
            "completude_pct": pct,
            "nulles": int(len(df) - non_null),
            "statut": "ok" if pct >= 80 else "nope"
        }
    report["mesures"]["completude"] = completeness
    avg_comp = round(sum(v["completude_pct"] for v in completeness.values()) / max(len(completeness), 1), 1)

    # 2. Unicité
    uniques = len(df.drop_duplicates())
    uniq_pct = round(uniques / max(len(df), 1) * 100, 1)
    report["mesures"]["unicite"] = {
        "lignes_uniques": uniques,
        "doublons": len(df) - uniques,
        "unicite_pct": uniq_pct,
        "statut": "ok" if uniq_pct >= 95 else "nope"
    }

    # 3. Validité géographique
    geo_score = 100.0
    lat_cols = [c for c in df.columns if c in ["lat", "stop_lat", "latitude"]]
    lon_cols = [c for c in df.columns if c in ["lon", "stop_lon", "longitude"]]
    if lat_cols and lon_cols:
        try:
            lat_col, lon_col = lat_cols[0], lon_cols[0]
            df_geo = df[[lat_col, lon_col]].copy()
            df_geo[lat_col] = pd.to_numeric(df_geo[lat_col], errors="coerce")
            df_geo[lon_col] = pd.to_numeric(df_geo[lon_col], errors="coerce")
            df_geo = df_geo.dropna()
            valid = (
                (df_geo[lat_col] >= 43.0) & (df_geo[lat_col] <= 44.5) &
                (df_geo[lon_col] >= 3.0)  & (df_geo[lon_col] <= 5.0)
            ).sum()
            geo_score = round(valid / max(len(df_geo), 1) * 100, 1)
            report["mesures"]["validite_geo"] = {
                "zone": "Hérault (lat 43.0-44.5, lon 3.0-5.0)",
                "coords_valides": int(valid),
                "coords_invalides": int(len(df_geo) - valid),
                "validite_geo_pct": geo_score,
                "statut": "ok" if geo_score >= 90 else "nope"
            }
        except Exception:
            pass

    # 4. Fraîcheur
    report["mesures"]["fraicheur"] = {
        "extraction_at": now_iso(),
        "source": "API temps réel" if "timestamp" in df.columns else "fichier CSV"
    }

    # Score global
    score = round(avg_comp * 0.4 + uniq_pct * 0.3 + geo_score * 0.3, 1)
    report["score_global"] = {
        "score": score,
        "statut": "Bonne" if score >= 85 else ("Acceptable" if score >= 70 else "Mauvaise"),
        "detail": {"completude_avg": avg_comp, "unicite": uniq_pct, "validite_geo": geo_score}
    }
    return report


def save_quality_report(reports: list):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = QUALITY_DIR / f"quality_report_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"   📋 Rapport qualité: {path.name}")


# ══════════════════════════════════════════════════════════════════
# BRONZE LAYER — EXTRACTION
# ══════════════════════════════════════════════════════════════════

def bronze_extract() -> dict:
    log.info("=" * 65)
    log.info("BRONZE LAYER — Extraction brute depuis les APIs")
    log.info("=" * 65)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {}
    sources = {
        "velomagg_stations":        API_VELOMAGG,
        "parkings":                 API_PARKINGS,
        "parking_spaces":           API_PARKING_SPACES,
        "ecocompteurs":             API_ECOCOUNTER,
        "gbfs_station_information": f"{GBFS_BASE}/station_information.json",
        "gbfs_station_status":      f"{GBFS_BASE}/station_status.json",
        "gbfs_free_bike_status":    f"{GBFS_BASE}/free_bike_status.json",
        "gbfs_vehicle_types":       f"{GBFS_BASE}/vehicle_types.json",
    }

    for name, url in sources.items():
        log.info(f"{name}...")
        data = fetch_api(url, name)
        if data is not None:
            path = BRONZE_DIR / f"{name}_{ts}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.info(f"   💾 {path.name}")
            results[name] = data

    log.info(f"Bronze terminé: {len(results)}/{len(sources)} sources")
    return results


# ══════════════════════════════════════════════════════════════════
# SILVER LAYER — TRANSFORMATION
# ══════════════════════════════════════════════════════════════════

def silver_transform(bronze: dict) -> dict:
    log.info("=" * 65)
    log.info("SILVER LAYER — Transformation et nettoyage")
    log.info("=" * 65)

    silver = {}
    quality_reports = []
    NOW = now_iso()

    # ── 1. VÉLOMAGG STATIONS (NGSI-LD) ───────────────────────────
    if "velomagg_stations" in bronze:
        log.info("velomagg_stations...")
        rows = []
        for s in bronze["velomagg_stations"]:
            lat, lon = ngsi_coords(s)
            total = safe_int(ngsi_val(s, "totalSlotNumber"))
            avail = safe_int(ngsi_val(s, "availableBikeNumber"))
            rows.append({
                "station_id":      s.get("id", ""),
                "station_code":    s.get("id", "").split(":")[-1],
                "adresse":         ngsi_address(s),
                "bikes_available": avail,
                "free_slots":      safe_int(ngsi_val(s, "freeSlotNumber")),
                "total_capacity":  total,
                "status":          str(ngsi_val(s, "status") or "unknown"),
                "lat":             lat,
                "lon":             lon,
                "taux_occupation": round(avail / max(total, 1) * 100, 1),
                "timestamp":       NOW,
                "type":            "velomagg",
            })
        df = pd.DataFrame(rows)
        df = df[df["lat"] != 0.0]
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        qr = compute_quality(df, "velomagg_stations")
        quality_reports.append(qr)
        df.to_parquet(SILVER_DIR / "velomagg_stations.parquet", index=False, compression="snappy")
        silver["velomagg_stations"] = df
        log.info(f"{len(df)} stations | score: {qr['score_global']['score']}/100 {qr['score_global']['statut']}")

    # ── 2. GBFS STATION INFORMATION ──────────────────────────────
    if "gbfs_station_information" in bronze:
        log.info("gbfs_station_information...")
        stations = bronze["gbfs_station_information"].get("data", {}).get("stations", [])
        rows = []
        for s in stations:
            rows.append({
                "station_id": s.get("station_id", ""),
                "nom":        s.get("name", ""),
                "lat":        safe_float(s.get("lat")),
                "lon":        safe_float(s.get("lon")),
                "capacite":   safe_int(s.get("capacity")),
                "adresse":    s.get("address", ""),
                "type":       "velomagg",
                "source":     "gbfs",
            })
        df = pd.DataFrame(rows)
        df = df[df["lat"] != 0.0]
        qr = compute_quality(df, "gbfs_station_information")
        quality_reports.append(qr)
        df.to_parquet(SILVER_DIR / "gbfs_station_information.parquet", index=False, compression="snappy")
        silver["gbfs_station_information"] = df
        log.info(f"{len(df)} stations GBFS | score: {qr['score_global']['score']}/100 {qr['score_global']['statut']}")

    # ── 3. GBFS STATION STATUS ────────────────────────────────────
    if "gbfs_station_status" in bronze:
        log.info("gbfs_station_status...")
        stations = bronze["gbfs_station_status"].get("data", {}).get("stations", [])
        rows = []
        for s in stations:
            lr = s.get("last_reported", 0)
            rows.append({
                "station_id":      s.get("station_id", ""),
                "bikes_available": safe_int(s.get("num_bikes_available")),
                "docks_available": safe_int(s.get("num_docks_available")),
                "is_installed":    safe_bool(s.get("is_installed")),
                "is_renting":      safe_bool(s.get("is_renting")),
                "is_returning":    safe_bool(s.get("is_returning")),
                "last_reported":   datetime.fromtimestamp(lr).isoformat() if lr else None,
                "timestamp":       NOW,
            })
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        qr = compute_quality(df, "gbfs_station_status")
        quality_reports.append(qr)
        df.to_parquet(SILVER_DIR / "gbfs_station_status.parquet", index=False, compression="snappy")
        silver["gbfs_station_status"] = df
        log.info(f"{len(df)} statuts | score: {qr['score_global']['score']}/100 {qr['score_global']['statut']}")

    # ── 4. GBFS FREE BIKE STATUS ──────────────────────────────────
    if "gbfs_free_bike_status" in bronze:
        log.info("gbfs_free_bike_status...")
        bikes = bronze["gbfs_free_bike_status"].get("data", {}).get("bikes", [])
        rows = []
        for b in bikes:
            rows.append({
                "bike_id":          b.get("bike_id", ""),
                "lat":              safe_float(b.get("lat")),
                "lon":              safe_float(b.get("lon")),
                "is_reserved":      safe_bool(b.get("is_reserved")),
                "is_disabled":      safe_bool(b.get("is_disabled")),
                "vehicle_type_id":  b.get("vehicle_type_id", ""),
                "timestamp":        NOW,
            })
        df = pd.DataFrame(rows)
        df = df[df["lat"] != 0.0]
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        qr = compute_quality(df, "gbfs_free_bike_status")
        quality_reports.append(qr)
        df.to_parquet(SILVER_DIR / "gbfs_free_bike_status.parquet", index=False, compression="snappy")
        silver["gbfs_free_bike_status"] = df
        log.info(f"{len(df)} vélos libres | score: {qr['score_global']['score']}/100 {qr['score_global']['statut']}")

    # ── 5. PARKINGS (NGSI-LD) ─────────────────────────────────────
    if "parkings" in bronze:
        log.info("parkings...")
        rows = []
        for p in bronze["parkings"]:
            lat, lon = ngsi_coords(p)
            pid   = p.get("id", "").split(":")[-1]
            total = safe_int(ngsi_val(p, "totalSpotNumber"))
            free  = safe_int(ngsi_val(p, "availableSpotNumber"))
            rows.append({
                "parking_id":      p.get("id", ""),
                "parking_code":    pid,
                "adresse":         ngsi_address(p) or f"Parking {pid} - Montpellier",
                "free_spots":      free,
                "total_spots":     total,
                "occupied_spots":  total - free,
                "taux_occupation": round((total - free) / max(total, 1) * 100, 1),
                "status":          str(ngsi_val(p, "status") or "unknown"),
                "lat":             lat,
                "lon":             lon,
                "timestamp":       NOW,
                "type":            "parking",
            })
        df = pd.DataFrame(rows)
        df = df[df["lat"] != 0.0]
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        qr = compute_quality(df, "parkings")
        quality_reports.append(qr)
        df.to_parquet(SILVER_DIR / "parkings.parquet", index=False, compression="snappy")
        silver["parkings"] = df
        log.info(f"{len(df)} parkings | score: {qr['score_global']['score']}/100 {qr['score_global']['statut']}")

    # ── 6. PARKING SPACES DÉTAIL (NGSI-LD) ───────────────────────
    if "parking_spaces" in bronze:
        log.info("parking_spaces...")
        rows = []
        for p in bronze["parking_spaces"]:
            rows.append({
                "parking_id":           p.get("id", ""),
                "nom":                  str(ngsi_val(p, "name") or ""),
                "adresse":              str(ngsi_val(p, "address") or ""),
                "lat":                  safe_float(ngsi_val(p, "latitude")),
                "lon":                  safe_float(ngsi_val(p, "longitude")),
                "type_parking":         str(ngsi_val(p, "parkingType") or ""),
                "typology":             str(ngsi_val(p, "typology") or ""),
                "domaniality":          str(ngsi_val(p, "domaniality") or ""),
                "total_places":         safe_int(ngsi_val(p, "parkingSpaceNumber")),
                "places_publiques":     safe_int(ngsi_val(p, "publicSpaces")),
                "places_restantes":     safe_int(ngsi_val(p, "remainingSpaces")),
                "places_pmr":           safe_int(ngsi_val(p, "disabledParkingNumber")),
                "voitures_electriques": safe_int(ngsi_val(p, "nb_voitures_electriques")),
                "hauteur_max_cm":       safe_int(ngsi_val(p, "maxHeight")),
                "proprietaire":         str(ngsi_val(p, "owner") or ""),
                "est_gratuit":          safe_bool(ngsi_val(p, "isFree")),
            })
        df = pd.DataFrame(rows)
        df = df[df["lat"] != 0.0]
        qr = compute_quality(df, "parking_spaces")
        quality_reports.append(qr)
        df.to_parquet(SILVER_DIR / "parking_spaces.parquet", index=False, compression="snappy")
        silver["parking_spaces"] = df
        log.info(f"{len(df)} parking spaces | score: {qr['score_global']['score']}/100 {qr['score_global']['statut']}")

    # ── 7. ECO-COMPTEURS (NGSI-LD) ────────────────────────────────
    if "ecocompteurs" in bronze:
        log.info("ecocompteurs...")
        rows = []
        for e in bronze["ecocompteurs"]:
            lat, lon = ngsi_coords(e)
            rows.append({
                "compteur_id": e.get("id", ""),
                "code":        e.get("id", "").split(":")[-1],
                "intensite":   safe_int(ngsi_val(e, "intensity")),
                "lat":         lat,
                "lon":         lon,
                "timestamp":   NOW,
            })
        df = pd.DataFrame(rows)
        df = df[df["lat"] != 0.0]
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        qr = compute_quality(df, "ecocompteurs")
        quality_reports.append(qr)
        df.to_parquet(SILVER_DIR / "ecocompteurs.parquet", index=False, compression="snappy")
        silver["ecocompteurs"] = df
        log.info(f"{len(df)} éco-compteurs | score: {qr['score_global']['score']}/100 {qr['score_global']['statut']}")

    # ── 8. FICHIERS CSV EXISTANTS ─────────────────────────────────
    log.info("Fichiers CSV existants...")
    for name, path in CSV_SOURCES.items():
        if not path.exists():
            log.warning(f"{name}: non trouvé ({path.name})")
            continue
        try:
            # Open-Meteo formatı için özel okuma
            if name == "meteo":
                df = pd.read_csv(
                    path, sep=",", skiprows=3,
                    encoding="utf-8-sig"
                )
            else:
                df = pd.read_csv(
                    path, sep=None, engine="python",
                    encoding="utf-8-sig"
                )   
            df.columns = [
                c.strip().lower()
                 .replace(" ", "_").replace("(", "").replace(")", "")
                 .replace("°c", "").replace("/", "_")
                for c in df.columns
            ]
            df = df.dropna(how="all")

            # Conversion dates
            for col in df.columns:
                if any(k in col for k in ["date", "time", "timestamp"]):
                    try:
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                    except Exception:
                        pass

            # Conversion numériques
            num_cols = ["lat", "lon", "stop_lat", "stop_lon", "latitude", "longitude",
                        "capacite", "intensite", "indice_qualite", "no2", "o3",
                        "pm10", "pm25", "bisiklet_sayisi"]
            for col in num_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            qr = compute_quality(df, name)
            quality_reports.append(qr)
            df.to_parquet(SILVER_DIR / f"{name}.parquet", index=False, compression="snappy")
            silver[name] = df
            log.info(f"{name}: {len(df)} lignes | score: {qr['score_global']['score']}/100 {qr['score_global']['statut']}")

        except Exception as e:
            log.warning(f"{name}: {e}")

    save_quality_report(quality_reports)
    log.info(f"Silver terminé: {len(silver)} datasets en Parquet")
    return silver


# ══════════════════════════════════════════════════════════════════
# GOLD LAYER — DUCKDB (HISTORIQUE + ANALYTIQUE)
# ══════════════════════════════════════════════════════════════════

def gold_duckdb(silver: dict):
    """
    GOLD DuckDB — données historiques et analytiques.
    Jointures:
    ① stations ↔ status       → JOIN sur station_id (FK)
    ② status ↔ qualite_air    → JOIN sur DATE(timestamp) = date
    ③ status ↔ meteo          → JOIN sur DATE(timestamp) = date
    ④ stations ↔ tam_stops    → JOIN géospatial (~500m)
    ⑤ stations ↔ ecocompteurs → JOIN géospatial (~300m)
    """
    log.info("=" * 65)
    log.info("GOLD — DuckDB (historique + analytique)")
    log.info("=" * 65)

    con = duckdb.connect(str(DUCKDB_PATH))

    # dim_stations
    log.info("dim_stations...")
    con.execute("DROP TABLE IF EXISTS dim_stations")
    con.execute("""
        CREATE TABLE dim_stations (
            station_id   VARCHAR PRIMARY KEY,
            station_code VARCHAR,
            nom          VARCHAR,
            adresse      VARCHAR,
            lat          DOUBLE,
            lon          DOUBLE,
            capacite     INTEGER,
            type         VARCHAR,
            source       VARCHAR,
            inserted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    if "gbfs_station_information" in silver:
        df = silver["gbfs_station_information"].copy()
        for _, r in df.iterrows():
            try:
                con.execute("""
                    INSERT OR IGNORE INTO dim_stations
                    VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                """, [r.get("station_id"), r.get("station_id"),
                      r.get("nom"), r.get("adresse"),
                      r.get("lat"), r.get("lon"),
                      safe_int(r.get("capacite")), "velomagg", "gbfs"])
            except Exception:
                pass
        n = con.execute("SELECT COUNT(*) FROM dim_stations").fetchone()[0]
        log.info(f"{n} stations Vélomagg")

    if "parking_spaces" in silver:
        df = silver["parking_spaces"].copy()
        for _, r in df.iterrows():
            try:
                con.execute("""
                    INSERT OR IGNORE INTO dim_stations
                    VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                """, [r.get("parking_id"), r.get("parking_id","").split(":")[-1],
                      r.get("nom"), r.get("adresse"),
                      r.get("lat"), r.get("lon"),
                      safe_int(r.get("total_places")), "parking", "ngsi"])
            except Exception:
                pass
        n = con.execute("SELECT COUNT(*) FROM dim_stations WHERE type='parking'").fetchone()[0]
        log.info(f"{n} parkings dans dim_stations")

    if "tam_stops" in silver:
        df = silver["tam_stops"].copy()
        if "stop_id" in df.columns:
            for _, r in df.iterrows():
                try:
                    con.execute("""
                        INSERT OR IGNORE INTO dim_stations
                        VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                    """, [str(r.get("stop_id","")), str(r.get("stop_code","")),
                          str(r.get("stop_name","")), "",
                          safe_float(r.get("stop_lat")), safe_float(r.get("stop_lon")),
                          0, "tam_stop", "gtfs"])
                except Exception:
                    pass
            n = con.execute("SELECT COUNT(*) FROM dim_stations WHERE type='tam_stop'").fetchone()[0]
            log.info(f"{n} arrêts TAM dans dim_stations")

    total = con.execute("SELECT COUNT(*) FROM dim_stations").fetchone()[0]
    log.info(f"dim_stations TOTAL: {total} entrées")

    # fact_velomagg_historique
    log.info("fact_velomagg_historique...")
    con.execute("DROP TABLE IF EXISTS fact_velomagg_historique")
    con.execute("""
        CREATE TABLE fact_velomagg_historique (
            station_id      VARCHAR,
            timestamp       TIMESTAMP,
            bisiklet_sayisi INTEGER
        )
    """)
    if "velomagg_historique" in silver:
        df = silver["velomagg_historique"].copy()
        col_map = {}
        for c in df.columns:
            if "station" in c: col_map[c] = "station_id"
            if "timestamp" in c or "time" in c: col_map[c] = "timestamp"
            if "bisiklet" in c or "bikes" in c or "nombre" in c: col_map[c] = "bisiklet_sayisi"
        df = df.rename(columns=col_map)
        cols = [c for c in ["station_id","timestamp","bisiklet_sayisi"] if c in df.columns]
        if cols:
            for _, r in df[cols].head(10000).iterrows():
                try:
                    con.execute(
                        f"INSERT INTO fact_velomagg_historique ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        [r[c] for c in cols]
                    )
                except Exception:
                    pass
            n = con.execute("SELECT COUNT(*) FROM fact_velomagg_historique").fetchone()[0]
            log.info(f"{n} entrées historique")

    # dim_qualite_air
    log.info("dim_qualite_air...")
    con.execute("DROP TABLE IF EXISTS dim_qualite_air")
    con.execute("""
        CREATE TABLE dim_qualite_air (
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
    if "qualite_air" in silver:
        df = silver["qualite_air"].copy()
        col_map = {}
        for c in df.columns:
            if "date" in c: col_map[c] = "date"
            if "code_qual" in c or "indice_qualite" in c: col_map[c] = "indice_qualite"
            if "lib_qual" in c or "libelle" in c: col_map[c] = "libelle_qualite"
            if "code_no2" in c or c == "no2": col_map[c] = "no2"
            if "code_so2" in c or c == "so2": col_map[c] = "so2"
            if "code_o3"  in c or c == "o3":  col_map[c] = "o3"
            if "code_pm10" in c or c == "pm10": col_map[c] = "pm10"
            if "code_pm25" in c or c == "pm25": col_map[c] = "pm25"
        df = df.rename(columns=col_map)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            df = df.dropna(subset=["date"])
            cols = [c for c in ["date","indice_qualite","libelle_qualite","no2","so2","o3","pm10","pm25"] if c in df.columns]
            for _, r in df[cols].head(500).iterrows():
                try:
                    con.execute(
                        f"INSERT OR IGNORE INTO dim_qualite_air ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        [r[c] for c in cols]
                    )
                except Exception:
                    pass
            n = con.execute("SELECT COUNT(*) FROM dim_qualite_air").fetchone()[0]
            log.info(f"{n} jours AQI")

    # dim_meteo
    log.info("dim_meteo...")
    con.execute("DROP TABLE IF EXISTS dim_meteo")
    con.execute("""
        CREATE TABLE dim_meteo (
            date              DATE PRIMARY KEY,
            temperature_max   DOUBLE,
            temperature_min   DOUBLE,
            precipitation_sum DOUBLE,
            wind_speed_max    DOUBLE,
            weather_code      INTEGER
        )
    """)
    if "meteo" in silver:
        df = silver["meteo"].copy()
        col_map = {}
        for c in df.columns:
            if c == "time": col_map[c] = "date"
            if "temperature_2m_max" in c: col_map[c] = "temperature_max"
            if "temperature_2m_min" in c: col_map[c] = "temperature_min"
            if "precipitation_sum" in c: col_map[c] = "precipitation_sum"
            if "wind_speed_10m_max" in c: col_map[c] = "wind_speed_max"
            if "weather_code" in c: col_map[c] = "weather_code"
        df = df.rename(columns=col_map)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            df = df.dropna(subset=["date"])
            cols = [c for c in ["date","temperature_max","temperature_min","precipitation_sum","wind_speed_max","weather_code"] if c in df.columns]
            for _, r in df[cols].iterrows():
                try:
                    con.execute(
                        f"INSERT OR IGNORE INTO dim_meteo ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        [r[c] for c in cols]
                    )
                except Exception:
                    pass
            n = con.execute("SELECT COUNT(*) FROM dim_meteo").fetchone()[0]
            log.info(f"   ✅ {n} jours météo")

    # dim_tam_stops
    log.info("dim_tam_stops...")
    con.execute("DROP TABLE IF EXISTS dim_tam_stops")
    con.execute("""
        CREATE TABLE dim_tam_stops (
            stop_id   VARCHAR PRIMARY KEY,
            stop_name VARCHAR,
            stop_lat  DOUBLE,
            stop_lon  DOUBLE,
            stop_code VARCHAR
        )
    """)
    if "tam_stops" in silver:
        df = silver["tam_stops"].copy()
        if "stop_id" in df.columns:
            for _, r in df.iterrows():
                try:
                    con.execute("INSERT OR IGNORE INTO dim_tam_stops VALUES (?,?,?,?,?)",
                        [str(r.get("stop_id","")), str(r.get("stop_name","")),
                         safe_float(r.get("stop_lat")), safe_float(r.get("stop_lon")),
                         str(r.get("stop_code",""))])
                except Exception:
                    pass
            n = con.execute("SELECT COUNT(*) FROM dim_tam_stops").fetchone()[0]
            log.info(f"{n} arrêts TAM")

    # dim_tam_routes
    log.info("dim_tam_routes...")
    con.execute("DROP TABLE IF EXISTS dim_tam_routes")
    con.execute("""
        CREATE TABLE dim_tam_routes (
            route_id    VARCHAR PRIMARY KEY,
            route_name  VARCHAR,
            route_type  INTEGER,
            route_color VARCHAR
        )
    """)
    if "tam_routes" in silver:
        df = silver["tam_routes"].copy()
        col_map = {}
        for c in df.columns:
            if "route_short_name" in c: col_map[c] = "route_name"
            if "route_color" in c and "text" not in c: col_map[c] = "route_color"
        df = df.rename(columns=col_map)
        if "route_id" in df.columns:
            cols = [c for c in ["route_id","route_name","route_type","route_color"] if c in df.columns]
            for _, r in df[cols].iterrows():
                try:
                    con.execute(
                        f"INSERT OR IGNORE INTO dim_tam_routes ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        [r[c] for c in cols]
                    )
                except Exception:
                    pass
            n = con.execute("SELECT COUNT(*) FROM dim_tam_routes").fetchone()[0]
            log.info(f"{n} lignes TAM")

    # dim_ecocompteurs
    log.info("dim_ecocompteurs...")
    con.execute("DROP TABLE IF EXISTS dim_ecocompteurs")
    con.execute("""
        CREATE TABLE dim_ecocompteurs (
            compteur_id VARCHAR PRIMARY KEY,
            code        VARCHAR,
            intensite   INTEGER,
            lat         DOUBLE,
            lon         DOUBLE,
            timestamp   TIMESTAMP
        )
    """)
    if "ecocompteurs" in silver:
        df = silver["ecocompteurs"].copy()
        for _, r in df.iterrows():
            try:
                con.execute("INSERT OR IGNORE INTO dim_ecocompteurs VALUES (?,?,?,?,?,?)",
                    [r.get("compteur_id"), r.get("code"),
                     safe_int(r.get("intensite")),
                     safe_float(r.get("lat")), safe_float(r.get("lon")),
                     str(r.get("timestamp",""))])
            except Exception:
                pass
        n = con.execute("SELECT COUNT(*) FROM dim_ecocompteurs").fetchone()[0]
        log.info(f"{n} éco-compteurs")

    # ref_co2_factors
    log.info("ref_co2_factors...")
    con.execute("DROP TABLE IF EXISTS ref_co2_factors")
    con.execute("""
        CREATE TABLE ref_co2_factors (
            mode         VARCHAR PRIMARY KEY,
            co2_g_per_km INTEGER,
            label        VARCHAR,
            source       VARCHAR
        )
    """)
    for mode, co2 in CO2_FACTORS.items():
        con.execute("INSERT INTO ref_co2_factors VALUES (?,?,?,?)",
            [mode, co2, f"{co2} g CO₂/km", "ADEME 2024"])
    log.info("CO₂ facteurs (ADEME 2024)")

    # ── VUES ANALYTIQUES ──────────────────────────────────────────
    log.info("Vues analytiques (jointures)...")

    # Vue 1: Mobilité complète
    # JOIN ①: stations ↔ status sur station_id
    # JOIN ②: status ↔ AQI sur DATE(timestamp)
    # JOIN ③: status ↔ meteo sur DATE(timestamp)
    con.execute("DROP VIEW IF EXISTS v_mobilite_complete")
    con.execute("""
        CREATE VIEW v_mobilite_complete AS
        SELECT
            s.station_id,
            s.nom,
            s.adresse,
            s.lat,
            s.lon,
            s.capacite,
            s.type,
            q.indice_qualite,
            q.libelle_qualite,
            q.no2,
            q.o3,
            q.pm10,
            m.temperature_max,
            m.temperature_min,
            m.precipitation_sum,
            m.wind_speed_max
        FROM dim_stations s
        LEFT JOIN dim_qualite_air q ON CURRENT_DATE = q.date
        LEFT JOIN dim_meteo m       ON CURRENT_DATE = m.date
        WHERE s.type = 'velomagg'
    """)
    log.info("v_mobilite_complete (stations + AQI + météo)")

    # Vue 2: Stations + arrêts TAM proches (< 500m)
    # JOIN ④: géospatial Vélomagg ↔ TAM
    con.execute("DROP VIEW IF EXISTS v_stations_tam_proches")
    con.execute("""
        CREATE VIEW v_stations_tam_proches AS
        SELECT
            s.station_id,
            s.nom            AS station_nom,
            s.lat            AS station_lat,
            s.lon            AS station_lon,
            t.stop_id,
            t.stop_name,
            t.stop_lat,
            t.stop_lon,
            ROUND(SQRT(POWER(s.lat - t.stop_lat, 2) +
                       POWER(s.lon - t.stop_lon, 2)) * 111000, 0) AS distance_m
        FROM dim_stations s
        JOIN dim_tam_stops t
            ON ABS(s.lat - t.stop_lat) < 0.005
           AND ABS(s.lon - t.stop_lon) < 0.005
        WHERE s.type = 'velomagg'
        ORDER BY s.station_id, distance_m
    """)
    log.info("v_stations_tam_proches (géospatial Vélomagg ↔ TAM)")

    # Vue 3: Stations + éco-compteurs proches (< 300m)
    # JOIN ⑤: géospatial Vélomagg ↔ éco-compteurs
    con.execute("DROP VIEW IF EXISTS v_stations_ecocompteurs")
    con.execute("""
        CREATE VIEW v_stations_ecocompteurs AS
        SELECT
            s.station_id,
            s.nom        AS station_nom,
            s.lat        AS station_lat,
            s.lon        AS station_lon,
            e.compteur_id,
            e.intensite,
            ROUND(SQRT(POWER(s.lat - e.lat, 2) +
                       POWER(s.lon - e.lon, 2)) * 111000, 0) AS distance_m
        FROM dim_stations s
        JOIN dim_ecocompteurs e
            ON ABS(s.lat - e.lat) < 0.003
           AND ABS(s.lon - e.lon) < 0.003
        WHERE s.type = 'velomagg'
        ORDER BY s.station_id, distance_m
    """)
    log.info("v_stations_ecocompteurs (géospatial Vélomagg ↔ compteurs)")

    # Vue 4: CO₂ économisé
    con.execute("DROP VIEW IF EXISTS v_co2_economies")
    con.execute("""
        CREATE VIEW v_co2_economies AS
        SELECT
            mode,
            co2_g_per_km,
            label,
            (SELECT co2_g_per_km FROM ref_co2_factors WHERE mode = 'voiture') - co2_g_per_km
                AS co2_economise_vs_voiture_g_per_km
        FROM ref_co2_factors
        ORDER BY co2_g_per_km
    """)
    log.info("v_co2_economies")

    con.close()
    log.info(f"Gold DuckDB terminé: {DUCKDB_PATH}")


# ══════════════════════════════════════════════════════════════════
# GOLD LAYER — POSTGRESQL (REAL-TIME)
# ══════════════════════════════════════════════════════════════════

def gold_postgres(silver: dict):
    """
    GOLD PostgreSQL — données temps réel uniquement.
    Tables: dim_stations, fact_station_status, fact_parkings_status, fact_free_bikes
    """
    try:
        import psycopg2
        con = psycopg2.connect(**PG_CONFIG)
        cur = con.cursor()
        log.info("=" * 65)
        log.info("🐘 GOLD — PostgreSQL (real-time)")
        log.info("=" * 65)

        cur.execute("CREATE SCHEMA IF NOT EXISTS modality;")

        # dim_stations
        cur.execute("""
            CREATE TABLE IF NOT EXISTS modality.dim_stations (
                station_id   VARCHAR PRIMARY KEY,
                nom          VARCHAR,
                adresse      VARCHAR,
                lat          DOUBLE PRECISION,
                lon          DOUBLE PRECISION,
                capacite     INTEGER,
                type         VARCHAR,
                source       VARCHAR,
                inserted_at  TIMESTAMP DEFAULT NOW()
            );
        """)
        if "gbfs_station_information" in silver:
            df = silver["gbfs_station_information"]
            for _, r in df.iterrows():
                cur.execute("""
                    INSERT INTO modality.dim_stations
                    (station_id, nom, adresse, lat, lon, capacite, type, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (station_id) DO UPDATE
                    SET nom=EXCLUDED.nom, lat=EXCLUDED.lat, lon=EXCLUDED.lon
                """, [r.get("station_id"), r.get("nom"), r.get("adresse"),
                      r.get("lat"), r.get("lon"), safe_int(r.get("capacite")),
                      "velomagg", "gbfs"])
            log.info(f"dim_stations: {len(df)} stations Vélomagg")

        # fact_station_status (REAL-TIME)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS modality.fact_station_status (
                id              SERIAL PRIMARY KEY,
                station_id      VARCHAR,
                bikes_available INTEGER,
                docks_available INTEGER,
                is_renting      BOOLEAN,
                is_returning    BOOLEAN,
                timestamp       TIMESTAMP,
                source          VARCHAR DEFAULT 'gbfs'
            );
        """)
        if "gbfs_station_status" in silver:
            df = silver["gbfs_station_status"]
            for _, r in df.iterrows():
                cur.execute("""
                    INSERT INTO modality.fact_station_status
                    (station_id, bikes_available, docks_available, is_renting, is_returning, timestamp, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, [r.get("station_id"), safe_int(r.get("bikes_available")),
                      safe_int(r.get("docks_available")),
                      safe_bool(r.get("is_renting")), safe_bool(r.get("is_returning")),
                      r.get("timestamp"), "gbfs"])
            log.info(f"fact_station_status: {len(df)} statuts (real-time)")

        # fact_parkings_status (REAL-TIME)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS modality.fact_parkings_status (
                id             SERIAL PRIMARY KEY,
                parking_id     VARCHAR,
                free_spots     INTEGER,
                total_spots    INTEGER,
                taux_occupation DOUBLE PRECISION,
                status         VARCHAR,
                lat            DOUBLE PRECISION,
                lon            DOUBLE PRECISION,
                timestamp      TIMESTAMP
            );
        """)
        if "parkings" in silver:
            df = silver["parkings"]
            for _, r in df.iterrows():
                cur.execute("""
                    INSERT INTO modality.fact_parkings_status
                    (parking_id, free_spots, total_spots, taux_occupation, status, lat, lon, timestamp)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, [r.get("parking_id"), safe_int(r.get("free_spots")),
                      safe_int(r.get("total_spots")), safe_float(r.get("taux_occupation")),
                      r.get("status"), r.get("lat"), r.get("lon"), r.get("timestamp")])
            log.info(f"fact_parkings_status: {len(df)} parkings (real-time)")

        # fact_free_bikes (REAL-TIME)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS modality.fact_free_bikes (
                bike_id         VARCHAR PRIMARY KEY,
                lat             DOUBLE PRECISION,
                lon             DOUBLE PRECISION,
                is_reserved     BOOLEAN,
                is_disabled     BOOLEAN,
                vehicle_type_id VARCHAR,
                timestamp       TIMESTAMP
            );
        """)
        if "gbfs_free_bike_status" in silver:
            df = silver["gbfs_free_bike_status"]
            for _, r in df.iterrows():
                cur.execute("""
                    INSERT INTO modality.fact_free_bikes
                    (bike_id, lat, lon, is_reserved, is_disabled, vehicle_type_id, timestamp)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (bike_id) DO UPDATE
                    SET lat=EXCLUDED.lat, lon=EXCLUDED.lon, timestamp=EXCLUDED.timestamp
                """, [r.get("bike_id"), r.get("lat"), r.get("lon"),
                      safe_bool(r.get("is_reserved")), safe_bool(r.get("is_disabled")),
                      r.get("vehicle_type_id"), r.get("timestamp")])
            log.info(f"fact_free_bikes: {len(df)} vélos libres (real-time)")

        con.commit()
        cur.close()
        con.close()
        log.info("Gold PostgreSQL terminé")

    except Exception as e:
        log.warning(f"PostgreSQL ignoré: {e}")
        log.info("   → Créer la DB avec: createdb modality_flow")
        log.info("   → Puis relancer: python3 etl_pipeline_v3.py --postgres")


# ══════════════════════════════════════════════════════════════════
# RAPPORT FINAL
# ══════════════════════════════════════════════════════════════════

def print_report():
    log.info("=" * 65)
    log.info("RAPPORT FINAL")
    log.info("=" * 65)

    con = duckdb.connect(str(DUCKDB_PATH))

    tables = ["dim_stations", "fact_velomagg_historique", "dim_qualite_air",
              "dim_meteo", "dim_tam_stops", "dim_tam_routes",
              "dim_ecocompteurs", "ref_co2_factors"]

    log.info("DuckDB — Gold Layer (historique + analytique):")
    for t in tables:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            log.info(f"{t:<35} {n:>8} lignes")
        except Exception:
            log.info(f"{t:<35} non disponible")

    log.info("")
    log.info("Test v_mobilite_complete:")
    try:
        df = con.execute("""
            SELECT nom, capacite, indice_qualite, temperature_max
            FROM v_mobilite_complete LIMIT 5
        """).fetchdf()
        log.info(f"\n{df.to_string(index=False)}")
    except Exception as e:
        log.warning(f"   {e}")

    log.info("")
    log.info("Silver (Parquet):")
    for f in sorted(SILVER_DIR.glob("*.parquet")):
        kb = f.stat().st_size // 1024
        log.info(f"{f.name:<45} {kb:>5} KB")

    log.info("")
    log.info("Bronze (JSON):")
    log.info(f"{len(list(BRONZE_DIR.glob('*.json')))} fichiers JSON horodatés")

    con.close()


# ══════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════

def run(use_postgres: bool = False):
    # Lock — aynı anda iki pipeline çalışmasın
    lock_file = open("/tmp/modality_etl.lock", "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        log.warning("Pipeline zaten çalısıyor, atlanıyor.")
        return
    start = datetime.now()
    log.info("MODALITY-FLOW ETL Pipeline v3 démarré")
    log.info(f"   Velo DIR : {VELO_DIR}")
    log.info(f"   ETL  DIR : {ETL_DIR}")
    log.info(f"   Mode     : {'Real-time (PG) + Historique (DuckDB)' if use_postgres else 'Historique (DuckDB) uniquement'}")

    create_dirs()

    # 1. BRONZE — Extraction brute API
    bronze = bronze_extract()

    # 2. SILVER — Transformation + Parquet + Qualité
    silver = silver_transform(bronze)

    # 3. GOLD DuckDB — Historique + Analytique
    gold_duckdb(silver)

    # 4. GOLD PostgreSQL — Real-time (optionnel)
    if use_postgres:
        gold_postgres(silver)

    # 5. Rapport
    print_report()

    elapsed = (datetime.now() - start).seconds
    log.info("=" * 65)
    log.info(f"Pipeline terminé en {elapsed}s")
    log.info(f"   Bronze  : {ETL_DIR}/bronze/")
    log.info(f"   Silver  : {ETL_DIR}/silver/")
    log.info(f"   Gold    : {DUCKDB_PATH}")
    log.info(f"   Quality : {ETL_DIR}/quality_reports/")
    log.info(f"   Logs    : {ETL_DIR}/logs/")
    log.info("=" * 65)


if __name__ == "__main__":
    use_pg = "--postgres" in sys.argv
    run(use_postgres=use_pg)
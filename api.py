"""
╔══════════════════════════════════════════════════════════════════╗
║         MODALITY-FLOW — FastAPI REST API                        ║
╠══════════════════════════════════════════════════════════════════╣
║  Endpoints:                                                     ║
║  GET  /                          → API status                   ║
║  GET  /stations                  → All stations (real-time)     ║
║  GET  /stations/{id}             → Single station               ║
║  POST /stations/{id}/predict     → ML prediction                ║
║  POST /route/co2                 → Lowest carbon route          ║
║  GET  /parkings                  → Parking availability         ║
║  GET  /free-bikes                → Free-floating bikes          ║
║  GET  /aqi                       → Air quality index            ║
║  GET  /meteo                     → Weather data                 ║
║  GET  /co2/factors               → CO₂ emission factors        ║
║  GET  /historique/{station_id}   → Historical data              ║
║  GET  /ml/features               → ML feature view              ║
║  GET  /tam/stops                 → TAM bus/tram stops           ║
║  GET  /tam/routes                → TAM lines                    ║
╠══════════════════════════════════════════════════════════════════╣
║  DOCS: http://localhost:8000/docs                               ║
║                                                                 ║
║  RUN:                                                           ║
║  /usr/local/bin/python3.14 -m uvicorn api:app --reload          ║
╚══════════════════════════════════════════════════════════════════╝
"""

import pickle
import numpy as np
import duckdb
import psycopg2
import psycopg2.extras
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════

import os

# Works both locally and on Railway
BASE_DIR = Path(os.environ.get("VELO_DIR", str(Path.home() / "Desktop" / "Velo")))
DUCKDB_PATH = BASE_DIR / "ETL" / "gold" / "modality_flow.duckdb"
MODEL_PATH  = BASE_DIR / "ML" / "models" / "availability_model.pkl"

# PostgreSQL connection config — real-time data
DATABASE_URL = os.environ.get(
    "DATABASE_PUBLIC_URL",
    "postgresql://postgres:postgres@localhost:5432/modality_flow"
)
# Parse DATABASE_URL for psycopg2
import urllib.parse
url = urllib.parse.urlparse(DATABASE_URL)
PG_CONFIG = {
    "host":     url.hostname,
    "port":     url.port or 5432,
    "database": url.path[1:],
    "user":     url.username,
    "password": url.password
}

# CO₂ emission factors in g/km — source: ADEME 2024
CO2_FACTORS = {
    "velo":    0,
    "tram":    4,
    "bus":     68,
    "voiture": 120,
    "marche":  0,
}

# Average speeds in km/h per transport mode
SPEEDS = {
    "velo":    15,
    "tram":    25,
    "bus":     20,
    "voiture": 30,
    "marche":  5,
}


# ══════════════════════════════════════════════════════════════════
# FASTAPI APP
# ══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Modality-Flow API",
    description="""
REST API for the Modality-Flow application — Éco-Mobilité 2026 Montpellier.

## Data sources
- **Real-time** (PostgreSQL): Vélomagg stations, parkings, free bikes — updated every minute
- **Historical** (DuckDB): Vélomagg history, AQI, weather, TAM stops
- **ML** (RandomForest): Bike availability prediction — R²=0.992, MAE=0.30

## CO₂ factors (ADEME 2024)
- Vélo: 0 g/km | Tram: 4 g/km | Bus: 68 g/km | Voiture: 120 g/km
    """,
    version="1.0.0",
    contact={"name": "Montpellier Méditerranée Métropole — Éco-Mobilité 2026"}
)

# Allow cross-origin requests — required for Flutter mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════
# LOAD ML MODEL AT STARTUP
# ══════════════════════════════════════════════════════════════════

ml_model    = None
ml_encoder  = None
ml_features = None

def load_ml_model():
    global ml_model, ml_encoder, ml_features
    if MODEL_PATH.exists():
        with open(MODEL_PATH, "rb") as f:
            data = pickle.load(f)
        ml_model    = data["model"]
        ml_encoder  = data["encoder"]
        ml_features = data["features"]
        print(f"✅ ML model loaded: {MODEL_PATH}")
    else:
        print(f"⚠️  ML model not found: {MODEL_PATH}")

load_ml_model()


# ══════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ══════════════════════════════════════════════════════════════════

def get_pg():
    """Open a PostgreSQL connection (real-time data)."""
    return psycopg2.connect(**PG_CONFIG)

def get_duck():
    """Open a DuckDB connection (historical/analytical data)."""
    return duckdb.connect(str(DUCKDB_PATH))


# ══════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ══════════════════════════════════════════════════════════════════

class RouteRequest(BaseModel):
    lat_a: float
    lon_a: float
    lat_b: float
    lon_b: float
    heure: Optional[int] = None
    precipitation: Optional[float] = 0.0
    bikes_available: Optional[int] = 5

class PredictRequest(BaseModel):
    station_id: str
    heure: Optional[int] = None
    jour_semaine: Optional[int] = None
    mois: Optional[int] = None
    jour_mois: Optional[int] = None
    precipitation: Optional[float] = 0.0
    temperature_max: Optional[float] = 20.0
    wind_speed_max: Optional[float] = 10.0
    indice_qualite: Optional[int] = 3


# ══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════

@app.get("/", tags=["Status"])
def root():
    """API health check — returns status and version info."""
    return {
        "status":      "✅ Modality-Flow API is running",
        "version":     "1.0.0",
        "timestamp":   datetime.now().isoformat(),
        "docs":        "/docs",
        "description": "Éco-Mobilité 2026 — Montpellier Méditerranée Métropole"
    }


# ── VÉLOMAGG STATIONS (Real-time — PostgreSQL) ────────────────────

@app.get("/stations", tags=["Vélomagg"])
def get_stations():
    """
    Returns all Vélomagg stations with real-time bike availability.
    Source: PostgreSQL — updated every minute via cron job.
    """
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                d.station_id,
                d.nom,
                d.adresse,
                d.lat,
                d.lon,
                d.capacite,
                f.bikes_available,
                f.docks_available,
                f.is_renting,
                f.is_returning,
                f.timestamp,
                ROUND(f.bikes_available * 100.0 / NULLIF(d.capacite, 0), 1) AS taux_disponibilite,
                CASE
                    WHEN f.bikes_available * 100.0 / NULLIF(d.capacite, 0) >= 50 THEN 'good'
                    WHEN f.bikes_available * 100.0 / NULLIF(d.capacite, 0) >= 20 THEN 'average'
                    ELSE 'low'
                END AS availability_level
            FROM modality.dim_stations d
            LEFT JOIN modality.fact_station_status f
                ON d.station_id = f.station_id
                AND f.timestamp = (
                    SELECT MAX(timestamp) FROM modality.fact_station_status
                    WHERE station_id = d.station_id
                )
            ORDER BY d.nom
        """)
        stations = cur.fetchall()
        cur.close()
        con.close()
        return {
            "count":     len(stations),
            "timestamp": datetime.now().isoformat(),
            "source":    "postgresql_realtime",
            "stations":  [dict(s) for s in stations]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stations/{station_id}", tags=["Vélomagg"])
def get_station(station_id: str):
    """
    Returns a single Vélomagg station with real-time bike availability.
    Source: PostgreSQL — updated every minute.
    """
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                d.station_id,
                d.nom,
                d.adresse,
                d.lat,
                d.lon,
                d.capacite,
                f.bikes_available,
                f.docks_available,
                f.is_renting,
                f.timestamp,
                ROUND(f.bikes_available * 100.0 / NULLIF(d.capacite, 0), 1) AS taux_disponibilite
            FROM modality.dim_stations d
            LEFT JOIN modality.fact_station_status f
                ON d.station_id = f.station_id
                AND f.timestamp = (
                    SELECT MAX(timestamp) FROM modality.fact_station_status
                    WHERE station_id = d.station_id
                )
            WHERE d.station_id = %s
        """, (station_id,))
        station = cur.fetchone()
        cur.close()
        con.close()
        if not station:
            raise HTTPException(status_code=404, detail=f"Station {station_id} not found")
        return dict(station)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── ML PREDICTION ─────────────────────────────────────────────────

@app.post("/stations/{station_id}/predict", tags=["ML"])
def predict_availability(station_id: str, req: PredictRequest = None):
    """
    Predicts bike availability for a given station using RandomForest ML model.
    Model performance: R²=0.992, MAE=0.30 bikes.
    Features: hour, day of week, month, weather, AQI, peak hours.
    """
    if ml_model is None:
        raise HTTPException(status_code=503, detail="ML model not loaded")

    # Use current time if not provided
    now          = datetime.now()
    heure        = req.heure         if req and req.heure         is not None else now.hour
    jour_semaine = req.jour_semaine  if req and req.jour_semaine  is not None else now.weekday()
    mois         = req.mois          if req and req.mois          is not None else now.month
    jour_mois    = req.jour_mois     if req and req.jour_mois     is not None else now.day
    precipitation= req.precipitation  if req else 0.0
    temperature  = req.temperature_max if req else 20.0
    wind_speed   = req.wind_speed_max  if req else 10.0
    aqi          = req.indice_qualite  if req else 3

    # Encode station ID for the model
    try:
        station_enc = ml_encoder.transform([station_id])[0]
    except Exception:
        station_enc = 0

    import pandas as pd
    X = pd.DataFrame([{
        "heure":             heure,
        "jour_semaine":      jour_semaine,
        "mois":              mois,
        "jour_mois":         jour_mois,
        "heure_pointe":      1 if (7 <= heure <= 9 or 17 <= heure <= 19) else 0,
        "weekend":           1 if jour_semaine >= 5 else 0,
        "temperature_max":   temperature,
        "precipitation_sum": precipitation,
        "wind_speed_max":    wind_speed,
        "indice_qualite":    aqi,
        "no2":               10,
        "o3":                50,
        "pm10":              15,
        "station_encoded":   station_enc,
    }])

    prediction = max(0, round(float(ml_model.predict(X)[0]), 1))

    return {
        "station_id": station_id,
        "prediction": {
            "bikes_predicted": prediction,
            "availability":    "good" if prediction >= 5 else "average" if prediction >= 2 else "low",
            "confidence":      "high (R²=0.992)"
        },
        "conditions": {
            "hour":         heure,
            "day_of_week":  jour_semaine,
            "is_peak_hour": bool(7 <= heure <= 9 or 17 <= heure <= 19),
            "is_weekend":   bool(jour_semaine >= 5),
            "precipitation": precipitation
        },
        "model":     "RandomForest — MAE=0.30 bikes",
        "timestamp": datetime.now().isoformat()
    }


# ── CO₂ ROUTE OPTIMIZATION ────────────────────────────────────────

@app.post("/route/co2", tags=["CO₂"])
def compute_route(req: RouteRequest):
    """
    Computes the lowest-carbon route from point A to point B.
    Uses Haversine distance + ADEME 2024 CO₂ emission factors.
    Returns all transport modes ranked by carbon footprint.
    """
    # Haversine distance (km)
    R    = 6371
    dlat = np.radians(req.lat_b - req.lat_a)
    dlon = np.radians(req.lon_b - req.lon_a)
    a    = (np.sin(dlat/2)**2 +
            np.cos(np.radians(req.lat_a)) *
            np.cos(np.radians(req.lat_b)) *
            np.sin(dlon/2)**2)
    distance_km = round(R * 2 * np.arcsin(np.sqrt(a)), 2)

    now   = datetime.now()
    heure = req.heure if req.heure is not None else now.hour

    routes = []
    for mode, co2_per_km in CO2_FACTORS.items():
        speed        = SPEEDS.get(mode, 20)
        duration_min = round(distance_km / speed * 60, 1)
        co2_total_g  = round(distance_km * co2_per_km, 1)
        co2_saved    = round(distance_km * CO2_FACTORS["voiture"] - co2_total_g, 1)

        # Scoring — lower is better
        score = co2_total_g

        # Penalty: cycling not recommended in rain
        if mode == "velo" and req.precipitation > 5:
            score += 50

        # Penalty: no bikes available at station
        if mode == "velo" and req.bikes_available == 0:
            score += 100

        # Penalty: walking not practical over 2 km
        if mode == "marche" and distance_km > 2:
            score += 200

        routes.append({
            "mode":             mode,
            "distance_km":      distance_km,
            "duration_min":     duration_min,
            "co2_g":            co2_total_g,
            "co2_saved_vs_car": co2_saved,
            "score":            score,
            "recommended":      False
        })

    # Sort by score and mark best option
    routes.sort(key=lambda x: x["score"])
    routes[0]["recommended"] = True
    best = routes[0]

    return {
        "distance_km": distance_km,
        "best_mode":   best["mode"],
        "co2_saved_g": best["co2_saved_vs_car"],
        "routes":      routes,
        "conditions": {
            "hour":            heure,
            "precipitation":   req.precipitation,
            "bikes_available": req.bikes_available
        },
        "co2_source":  "ADEME 2024",
        "timestamp":   datetime.now().isoformat()
    }


# ── PARKINGS (Real-time — PostgreSQL) ────────────────────────────

@app.get("/parkings", tags=["Parkings"])
def get_parkings():
    """
    Returns all parking facilities with real-time occupancy.
    Source: PostgreSQL — updated every 5 minutes via cron job.
    """
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                parking_id,
                free_spots,
                total_spots,
                taux_occupation,
                status,
                lat,
                lon,
                timestamp,
                CASE
                    WHEN taux_occupation >= 80 THEN 'full'
                    WHEN taux_occupation >= 60 THEN 'busy'
                    WHEN taux_occupation >= 40 THEN 'moderate'
                    ELSE 'available'
                END AS occupancy_level
            FROM modality.fact_parkings_status
            WHERE timestamp = (SELECT MAX(timestamp) FROM modality.fact_parkings_status)
            ORDER BY taux_occupation DESC
        """)
        parkings = cur.fetchall()
        cur.close()
        con.close()
        return {
            "count":     len(parkings),
            "timestamp": datetime.now().isoformat(),
            "source":    "postgresql_realtime",
            "parkings":  [dict(p) for p in parkings]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── FREE BIKES (Real-time — PostgreSQL) ──────────────────────────

@app.get("/free-bikes", tags=["Vélomagg"])
def get_free_bikes():
    """
    Returns all free-floating bikes with current GPS location.
    Source: PostgreSQL — updated every minute via cron job.
    """
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                bike_id,
                lat,
                lon,
                is_reserved,
                is_disabled,
                vehicle_type_id,
                timestamp
            FROM modality.fact_free_bikes
            WHERE is_disabled = false
            ORDER BY timestamp DESC
        """)
        bikes = cur.fetchall()
        cur.close()
        con.close()
        return {
            "count":     len(bikes),
            "timestamp": datetime.now().isoformat(),
            "source":    "postgresql_realtime",
            "bikes":     [dict(b) for b in bikes]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AIR QUALITY INDEX (DuckDB — Atmo Occitanie) ──────────────────

@app.get("/aqi", tags=["Environment"])
def get_aqi(date: Optional[str] = None):
    """
    Returns air quality index (AQI) data for Montpellier.
    Source: DuckDB — Atmo Occitanie (498 days of data).
    Optional: filter by date (YYYY-MM-DD).
    """
    try:
        con = get_duck()
        if date:
            df = con.execute(
                "SELECT * FROM dim_qualite_air WHERE date = ?", [date]
            ).fetchdf()
        else:
            df = con.execute(
                "SELECT * FROM dim_qualite_air ORDER BY date DESC LIMIT 7"
            ).fetchdf()
        con.close()

        records = df.to_dict("records")
        for r in records:
            if "date" in r and hasattr(r["date"], "isoformat"):
                r["date"] = r["date"].isoformat()

        return {
            "today":     records[0] if records else {},
            "history":   records,
            "source":    "atmo_occitanie",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── WEATHER (DuckDB — Open-Meteo) ────────────────────────────────

@app.get("/meteo", tags=["Environment"])
def get_meteo(date: Optional[str] = None):
    """
    Returns weather data for Montpellier.
    Source: DuckDB — Open-Meteo API (366 days of data).
    Optional: filter by date (YYYY-MM-DD).
    """
    try:
        con = get_duck()
        if date:
            df = con.execute(
                "SELECT * FROM dim_meteo WHERE date = ?", [date]
            ).fetchdf()
        else:
            df = con.execute(
                "SELECT * FROM dim_meteo ORDER BY date DESC LIMIT 7"
            ).fetchdf()
        con.close()

        records = df.to_dict("records")
        for r in records:
            if "date" in r and hasattr(r["date"], "isoformat"):
                r["date"] = r["date"].isoformat()

        return {
            "today":     records[0] if records else {},
            "history":   records,
            "source":    "open_meteo",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── CO₂ FACTORS (DuckDB) ─────────────────────────────────────────

@app.get("/co2/factors", tags=["CO₂"])
def get_co2_factors():
    """
    Returns CO₂ emission factors per transport mode.
    Source: DuckDB — ADEME 2024 reference data.
    """
    try:
        con = get_duck()
        df  = con.execute(
            "SELECT * FROM ref_co2_factors ORDER BY co2_g_per_km"
        ).fetchdf()
        con.close()
        return {
            "factors":   df.to_dict("records"),
            "source":    "ADEME 2024",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── HISTORICAL DATA (DuckDB) ─────────────────────────────────────

@app.get("/historique/{station_id}", tags=["Historical"])
def get_historique(station_id: str, limit: int = 100):
    """
    Returns historical bike availability for a given station.
    Source: DuckDB — fact_velomagg_historique (644,880 rows, 2024-2026).
    """
    try:
        con = get_duck()
        df  = con.execute("""
            SELECT
                station_id,
                timestamp,
                bisiklet_sayisi        AS bikes_available,
                EXTRACT(HOUR  FROM timestamp) AS hour,
                EXTRACT(DOW   FROM timestamp) AS day_of_week,
                EXTRACT(MONTH FROM timestamp) AS month
            FROM fact_velomagg_historique
            WHERE station_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, [station_id, limit]).fetchdf()
        con.close()

        records = df.to_dict("records")
        for r in records:
            if "timestamp" in r and hasattr(r["timestamp"], "isoformat"):
                r["timestamp"] = r["timestamp"].isoformat()

        return {
            "station_id": station_id,
            "count":      len(records),
            "source":     "duckdb_historique",
            "data":       records
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── ML FEATURES (DuckDB) ─────────────────────────────────────────

@app.get("/ml/features", tags=["ML"])
def get_ml_features(station_id: Optional[str] = None, limit: int = 100):
    """
    Returns ML feature view combining bike history, weather and AQI.
    Includes derived features: peak_hour flag, weekend flag.
    Source: DuckDB — v_ml_features view.
    """
    try:
        con = get_duck()
        if station_id:
            df = con.execute("""
                SELECT * FROM v_ml_features
                WHERE station_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, [station_id, limit]).fetchdf()
        else:
            df = con.execute("""
                SELECT * FROM v_ml_features
                ORDER BY timestamp DESC
                LIMIT ?
            """, [limit]).fetchdf()
        con.close()

        records = df.to_dict("records")
        for r in records:
            if "timestamp" in r and hasattr(r["timestamp"], "isoformat"):
                r["timestamp"] = r["timestamp"].isoformat()

        return {
            "count":  len(records),
            "source": "duckdb_ml_features",
            "data":   records
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── TAM STOPS & ROUTES (DuckDB — GTFS) ──────────────────────────

@app.get("/tam/stops", tags=["TAM"])
def get_tam_stops():
    """
    Returns all TAM public transport stops (2,112 stops).
    Source: DuckDB — GTFS TAM static data.
    """
    try:
        con = get_duck()
        df  = con.execute("SELECT * FROM dim_tam_stops").fetchdf()
        con.close()
        return {
            "count":  len(df),
            "source": "gtfs_tam",
            "stops":  df.to_dict("records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tam/routes", tags=["TAM"])
def get_tam_routes():
    """
    Returns all TAM bus and tram lines (43 lines).
    Source: DuckDB — GTFS TAM static data.
    """
    try:
        con = get_duck()
        df  = con.execute("SELECT * FROM dim_tam_routes").fetchdf()
        con.close()
        return {
            "count":  len(df),
            "source": "gtfs_tam",
            "routes": df.to_dict("records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    import sys
    sys.path.insert(0, "/Users/ozlemdechamps/Desktop/Velo")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
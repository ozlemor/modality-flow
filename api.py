"""
MODALITY-FLOW — FastAPI REST API v2
100% PostgreSQL — Railway compatible

Endpoints:
  GET  /                          -> API status
  GET  /stations                  -> All stations (real-time)
  GET  /stations/{id}             -> Single station
  POST /stations/{id}/predict     -> ML prediction (v2)
  POST /route/co2                 -> Lowest carbon route
  GET  /parkings                  -> Parking availability
  GET  /free-bikes                -> Free-floating bikes
  GET  /aqi                       -> Air quality index
  GET  /meteo                     -> Weather data
  GET  /co2/factors               -> CO2 emission factors
  GET  /historique/{station_id}   -> Historical data
  GET  /ml/features               -> ML feature view
  GET  /tam/stops                 -> TAM bus/tram stops
  GET  /tam/routes                -> TAM lines
  GET  /demographics              -> INSEE commune demographics
  GET  /fairness                  -> Spatial fairness analysis
  POST /journey                   -> Multimodal journey planner (ML + TAM + CO2)

Docs: http://localhost:8000/docs

Run (local):
  uvicorn api:app --host 0.0.0.0 --port 8000
"""

import os
import math
import pickle
import joblib
import numpy as np
import psycopg2
import psycopg2.extras
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- CONFIG -------------------------------------------------------------------

BASE_DIR   = Path(os.environ.get("VELO_DIR", "/app"))
MODEL_PATH = BASE_DIR / "ML" / "models" / "availability_model.pkl"

DATABASE_URL = os.environ.get(
    "DATABASE_PUBLIC_URL",
    "postgresql://postgres:postgres@localhost:5432/modality_flow"
)

import urllib.parse
_url = urllib.parse.urlparse(DATABASE_URL)
PG_CONFIG = {
    "host":     _url.hostname,
    "port":     _url.port or 5432,
    "database": _url.path[1:],
    "user":     _url.username,
    "password": _url.password,
    "sslmode":  "require" if "railway" in DATABASE_URL else "prefer"
}

# CO2 emission factors in g/km — source: ADEME 2024
CO2_FACTORS = {
    "velo":    0,
    "tram":    4,
    "bus":     68,
    "voiture": 120,
    "marche":  0,
}

SPEEDS = {
    "velo":    15,
    "tram":    25,
    "bus":     20,
    "voiture": 30,
    "marche":  5,
}

# Montpellier demographic values — INSEE RP 2020 (commune 34172)
# Static for all Velomagg stations (all located in Montpellier)
MONTPELLIER_DEMO = {
    "pct_young_adult": 31.20,
    "pct_active":      38.05,
    "pct_65plus":      18.85,
    "pct_high_income": 12.79,
    "pct_low_income":  22.46,
    "population":      299096,
}


# --- APP ----------------------------------------------------------------------

app = FastAPI(
    title="Modality-Flow API",
    description="""
REST API for the Modality-Flow application — Eco-Mobilite 2026 Montpellier.

## Data sources
- **Real-time** (PostgreSQL): Velomagg stations, parkings, free bikes
- **Historical** (PostgreSQL): Velomagg history 2024-2026, AQI, weather, TAM
- **ML** (RandomForest v2): Bike availability prediction — R2=0.9977, MAE=0.14
- **Demographics** (INSEE RP 2020): Commune-level socio-demographic features

## CO2 factors (ADEME 2024)
Velo: 0 g/km | Tram: 4 g/km | Bus: 68 g/km | Voiture: 120 g/km
    """,
    version="2.1.0",
    contact={"name": "Montpellier Mediterranee Metropole — Eco-Mobilite 2026"}
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- ML MODEL -----------------------------------------------------------------

ml_model    = None
ml_encoder  = None
ml_features = None

def load_ml_model():
    global ml_model, ml_encoder, ml_features
    if not MODEL_PATH.exists():
        print(f"ML model not found: {MODEL_PATH}")
        return
    try:
        try:
            with open(MODEL_PATH, "rb") as f:
                data = pickle.load(f)
        except Exception:
            data = joblib.load(MODEL_PATH)
        ml_model    = data["model"]
        ml_encoder  = data["encoder"]
        ml_features = data["features"]
        print(f"ML model loaded: {MODEL_PATH}")
        print(f"  Features ({len(ml_features)}): {ml_features}")
    except Exception as e:
        print(f"ML model could not be loaded: {e}")
        print("  Predict endpoint will return 503 until model is available.")

load_ml_model()


# --- DATABASE -----------------------------------------------------------------

def get_pg():
    return psycopg2.connect(**PG_CONFIG)


# --- SCHEMAS ------------------------------------------------------------------

class RouteRequest(BaseModel):
    lat_a: float
    lon_a: float
    lat_b: float
    lon_b: float
    heure: Optional[int] = None
    precipitation: Optional[float] = 0.0
    bikes_available: Optional[int] = 5

class JourneyRequest(BaseModel):
    lat_a: float
    lon_a: float
    lat_b: float
    lon_b: float
    heure: Optional[int]           = None
    jour_semaine: Optional[int]    = None
    mois: Optional[int]            = None
    jour_mois: Optional[int]       = None
    precipitation: Optional[float] = 0.0
    temperature: Optional[float]   = 20.0
    wind_speed: Optional[float]    = 10.0
    indice_qualite: Optional[int]  = 3

class PredictRequest(BaseModel):
    heure: Optional[int] = None
    jour_semaine: Optional[int] = None
    mois: Optional[int] = None
    jour_mois: Optional[int] = None
    precipitation: Optional[float] = 0.0
    temperature_max: Optional[float] = 20.0
    wind_speed_max: Optional[float] = 10.0
    indice_qualite: Optional[int] = 3


# --- ENDPOINTS ----------------------------------------------------------------

@app.get("/", tags=["Status"])
def root():
    return {
        "status":      "Modality-Flow API is running",
        "version":     "2.1.0",
        "timestamp":   datetime.now().isoformat(),
        "docs":        "/docs",
        "database":    "Railway PostgreSQL",
        "ml_model":    "RandomForest v2 — R2=0.9977, MAE=0.14",
        "description": "Eco-Mobilite 2026 — Montpellier Mediterranee Metropole"
    }


# -- STATIONS (real-time) ------------------------------------------------------

@app.get("/stations", tags=["Velomagg"])
def get_stations():
    """All Velomagg stations with real-time bike availability."""
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
            FROM public.dim_stations d
            LEFT JOIN modality.fact_station_status f
                ON d.station_id = f.station_id
                AND f.timestamp = (
                    SELECT MAX(timestamp) FROM modality.fact_station_status
                    WHERE station_id = d.station_id
                )
            WHERE d.type = 'velomagg'
            ORDER BY d.nom
        """)
        stations = cur.fetchall()
        cur.close(); con.close()
        return {
            "count":     len(stations),
            "timestamp": datetime.now().isoformat(),
            "source":    "postgresql_realtime",
            "stations":  [dict(s) for s in stations]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stations/{station_id}", tags=["Velomagg"])
def get_station(station_id: str):
    """Single Velomagg station with real-time bike availability."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                d.station_id, d.nom, d.adresse, d.lat, d.lon, d.capacite,
                f.bikes_available, f.docks_available, f.is_renting, f.timestamp,
                ROUND(f.bikes_available * 100.0 / NULLIF(d.capacite, 0), 1) AS taux_disponibilite
            FROM public.dim_stations d
            LEFT JOIN modality.fact_station_status f
                ON d.station_id = f.station_id
                AND f.timestamp = (
                    SELECT MAX(timestamp) FROM modality.fact_station_status
                    WHERE station_id = d.station_id
                )
            WHERE d.station_id = %s
        """, (station_id,))
        station = cur.fetchone()
        cur.close(); con.close()
        if not station:
            raise HTTPException(status_code=404, detail=f"Station {station_id} not found")
        return dict(station)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- ML PREDICTION -------------------------------------------------------------

@app.post("/stations/{station_id}/predict", tags=["ML"])
def predict_availability(station_id: str, req: PredictRequest = None):
    """
    Predicts bike availability using RandomForest ML model v2.

    Model features: time + geographic (lat, lon, capacite, dist_centre_km)
    + weather + air quality + demographics (INSEE 2020).

    Station geographic data is fetched automatically from the database.
    R2=0.9977, MAE=0.14 bikes.
    """
    if ml_model is None:
        raise HTTPException(status_code=503, detail="ML model not loaded")

    # Fetch station geographic data from DB
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT lat, lon, capacite,
                SQRT(
                    POWER((lat - 43.6109) * 111, 2) +
                    POWER((lon - 3.8763)  * 85,  2)
                ) AS dist_centre_km
            FROM public.dim_stations
            WHERE station_id = %s
        """, (station_id,))
        station = cur.fetchone()
        cur.close(); con.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")

    if not station:
        raise HTTPException(status_code=404, detail=f"Station {station_id} not found")

    # Time defaults
    now          = datetime.now()
    heure        = req.heure        if req and req.heure        is not None else now.hour
    jour_semaine = req.jour_semaine if req and req.jour_semaine is not None else now.weekday()
    mois         = req.mois         if req and req.mois         is not None else now.month
    jour_mois    = req.jour_mois    if req and req.jour_mois    is not None else now.day
    precipitation= req.precipitation  if req else 0.0
    temperature  = req.temperature_max if req else 20.0
    wind_speed   = req.wind_speed_max  if req else 10.0
    aqi          = req.indice_qualite  if req else 3

    # Encode station_id
    try:
        station_enc = ml_encoder.transform([station_id])[0]
    except Exception:
        station_enc = 0

    # Build feature row — must match ml_features order exactly
    row = {
        "heure":             heure,
        "jour_semaine":      jour_semaine,
        "mois":              mois,
        "jour_mois":         jour_mois,
        "heure_pointe":      1 if (7 <= heure <= 9 or 17 <= heure <= 19) else 0,
        "weekend":           1 if jour_semaine >= 5 else 0,
        "lat":               float(station["lat"]),
        "lon":               float(station["lon"]),
        "capacite":          float(station["capacite"]),
        "dist_centre_km":    float(station["dist_centre_km"]),
        "station_encoded":   station_enc,
        "temperature_max":   temperature,
        "precipitation_sum": precipitation,
        "wind_speed_max":    wind_speed,
        "indice_qualite":    aqi,
        "no2":               10,
        "o3":                50,
        "pm10":              15,
        **MONTPELLIER_DEMO,
    }

    X          = pd.DataFrame([row])[ml_features].fillna(0)
    prediction = max(0, round(float(ml_model.predict(X)[0]), 1))

    return {
        "station_id": station_id,
        "prediction": {
            "bikes_predicted":  prediction,
            "availability":     "good" if prediction >= 5 else "average" if prediction >= 2 else "low",
            "confidence":       "high (R2=0.9977, MAE=0.14)"
        },
        "conditions": {
            "hour":          heure,
            "day_of_week":   jour_semaine,
            "is_peak_hour":  bool(7 <= heure <= 9 or 17 <= heure <= 19),
            "is_weekend":    bool(jour_semaine >= 5),
            "precipitation": precipitation,
            "temperature":   temperature,
        },
        "station": {
            "lat":           float(station["lat"]),
            "lon":           float(station["lon"]),
            "capacite":      float(station["capacite"]),
            "dist_centre_km": round(float(station["dist_centre_km"]), 2),
        },
        "model":     "RandomForest v2 — geo + demographics + weather",
        "timestamp": datetime.now().isoformat()
    }


# -- CO2 ROUTE OPTIMIZATION ----------------------------------------------------

@app.post("/route/co2", tags=["CO2"])
def compute_route(req: RouteRequest):
    """
    Computes the lowest-carbon route from A to B.
    Haversine distance + ADEME 2024 CO2 factors.
    """
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
        duration_min = round(distance_km / SPEEDS[mode] * 60, 1)
        co2_total_g  = round(distance_km * co2_per_km, 1)
        co2_saved    = round(distance_km * CO2_FACTORS["voiture"] - co2_total_g, 1)

        score = co2_total_g
        if mode == "velo"   and req.precipitation > 5:    score += 50
        if mode == "velo"   and req.bikes_available == 0: score += 100
        if mode == "marche" and distance_km > 2:          score += 200

        routes.append({
            "mode":             mode,
            "distance_km":      distance_km,
            "duration_min":     duration_min,
            "co2_g":            co2_total_g,
            "co2_saved_vs_car": co2_saved,
            "score":            score,
            "recommended":      False
        })

    routes.sort(key=lambda x: x["score"])
    routes[0]["recommended"] = True

    return {
        "distance_km": distance_km,
        "best_mode":   routes[0]["mode"],
        "co2_saved_g": routes[0]["co2_saved_vs_car"],
        "routes":      routes,
        "conditions": {
            "hour":            heure,
            "precipitation":   req.precipitation,
            "bikes_available": req.bikes_available
        },
        "co2_source":  "ADEME 2024",
        "timestamp":   datetime.now().isoformat()
    }


# -- PARKINGS (real-time) ------------------------------------------------------

@app.get("/parkings", tags=["Parkings"])
def get_parkings():
    """All parkings with real-time occupancy."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT DISTINCT ON (parking_id)
                parking_id, free_spots, total_spots, taux_occupation,
                status, lat, lon, timestamp,
                CASE
                    WHEN taux_occupation >= 80 THEN 'full'
                    WHEN taux_occupation >= 60 THEN 'busy'
                    WHEN taux_occupation >= 40 THEN 'moderate'
                    ELSE 'available'
                END AS occupancy_level
            FROM modality.fact_parkings_status
            ORDER BY parking_id, timestamp DESC
        """)
        parkings = cur.fetchall()
        cur.close(); con.close()
        return {
            "count":     len(parkings),
            "timestamp": datetime.now().isoformat(),
            "source":    "postgresql_realtime",
            "parkings":  [dict(p) for p in parkings]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- FREE BIKES (real-time) ----------------------------------------------------

@app.get("/free-bikes", tags=["Velomagg"])
def get_free_bikes():
    """All free-floating bikes with current GPS location."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT bike_id, lat, lon, is_reserved, is_disabled,
                   vehicle_type_id, timestamp
            FROM modality.fact_free_bikes
            WHERE is_disabled = false
            ORDER BY timestamp DESC
        """)
        bikes = cur.fetchall()
        cur.close(); con.close()
        return {
            "count":     len(bikes),
            "timestamp": datetime.now().isoformat(),
            "source":    "postgresql_realtime",
            "bikes":     [dict(b) for b in bikes]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- AIR QUALITY ---------------------------------------------------------------

@app.get("/aqi", tags=["Environment"])
def get_aqi(date: Optional[str] = None):
    """Air quality index — Atmo Occitanie (498 days)."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if date:
            cur.execute("SELECT * FROM public.dim_qualite_air WHERE date = %s", (date,))
        else:
            cur.execute("SELECT * FROM public.dim_qualite_air ORDER BY date DESC LIMIT 7")
        records = cur.fetchall()
        cur.close(); con.close()
        data = [dict(r) for r in records]
        for r in data:
            if r.get("date"):
                r["date"] = str(r["date"])
        return {"today": data[0] if data else {}, "history": data,
                "source": "atmo_occitanie", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- WEATHER -------------------------------------------------------------------

@app.get("/meteo", tags=["Environment"])
def get_meteo(date: Optional[str] = None):
    """Weather data for Montpellier — Open-Meteo (366 days)."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if date:
            cur.execute("SELECT * FROM public.dim_meteo WHERE date = %s", (date,))
        else:
            cur.execute("SELECT * FROM public.dim_meteo ORDER BY date DESC LIMIT 7")
        records = cur.fetchall()
        cur.close(); con.close()
        data = [dict(r) for r in records]
        for r in data:
            if r.get("date"):
                r["date"] = str(r["date"])
        return {"today": data[0] if data else {}, "history": data,
                "source": "open_meteo", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- CO2 FACTORS ---------------------------------------------------------------

@app.get("/co2/factors", tags=["CO2"])
def get_co2_factors():
    """CO2 emission factors per transport mode — ADEME 2024."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM public.ref_co2_factors ORDER BY co2_g_per_km")
        records = cur.fetchall()
        cur.close(); con.close()
        return {"factors": [dict(r) for r in records],
                "source": "ADEME 2024", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- HISTORICAL DATA -----------------------------------------------------------

@app.get("/historique/{station_id}", tags=["Historical"])
def get_historique(station_id: str, limit: int = 100):
    """Historical bike availability for a given station."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                station_id, timestamp,
                bisiklet_sayisi        AS bikes_available,
                EXTRACT(HOUR  FROM timestamp) AS hour,
                EXTRACT(DOW   FROM timestamp) AS day_of_week,
                EXTRACT(MONTH FROM timestamp) AS month
            FROM public.fact_velomagg_historique
            WHERE station_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (station_id, limit))
        records = cur.fetchall()
        cur.close(); con.close()
        data = [dict(r) for r in records]
        for r in data:
            if r.get("timestamp"):
                r["timestamp"] = str(r["timestamp"])
        return {"station_id": station_id, "count": len(data),
                "source": "postgresql_historique", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- ML FEATURES ---------------------------------------------------------------

@app.get("/ml/features", tags=["ML"])
def get_ml_features(station_id: Optional[str] = None, limit: int = 100):
    """ML feature view — history + weather + AQI joined."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        query = """
            SELECT
                h.station_id, h.timestamp,
                h.bisiklet_sayisi AS bikes_available,
                EXTRACT(HOUR  FROM h.timestamp) AS hour,
                EXTRACT(DOW   FROM h.timestamp) AS day_of_week,
                EXTRACT(MONTH FROM h.timestamp) AS month,
                CASE WHEN EXTRACT(HOUR FROM h.timestamp) BETWEEN 7 AND 9
                          OR EXTRACT(HOUR FROM h.timestamp) BETWEEN 17 AND 19
                     THEN 1 ELSE 0 END AS is_peak_hour,
                CASE WHEN EXTRACT(DOW FROM h.timestamp) IN (0,6) THEN 1 ELSE 0 END AS is_weekend,
                m.temperature_max, m.precipitation_sum, m.wind_speed_max,
                q.indice_qualite AS aqi, q.no2, q.o3, q.pm10
            FROM public.fact_velomagg_historique h
            LEFT JOIN public.dim_meteo m ON CAST(h.timestamp AS DATE) = m.date
            LEFT JOIN public.dim_qualite_air q ON CAST(h.timestamp AS DATE) = q.date
            WHERE h.bisiklet_sayisi IS NOT NULL
        """
        if station_id:
            query += " AND h.station_id = %s ORDER BY h.timestamp DESC LIMIT %s"
            cur.execute(query, (station_id, limit))
        else:
            query += " ORDER BY h.timestamp DESC LIMIT %s"
            cur.execute(query, (limit,))
        records = cur.fetchall()
        cur.close(); con.close()
        data = [dict(r) for r in records]
        for r in data:
            if r.get("timestamp"):
                r["timestamp"] = str(r["timestamp"])
        return {"count": len(data), "source": "postgresql_ml_features", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- TAM -----------------------------------------------------------------------

@app.get("/tam/stops", tags=["TAM"])
def get_tam_stops():
    """All TAM public transport stops (2,112 stops)."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM public.dim_tam_stops")
        records = cur.fetchall()
        cur.close(); con.close()
        return {"count": len(records), "source": "gtfs_tam",
                "stops": [dict(r) for r in records]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tam/routes", tags=["TAM"])
def get_tam_routes():
    """All TAM bus and tram lines (43 lines)."""
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM public.dim_tam_routes")
        records = cur.fetchall()
        cur.close(); con.close()
        return {"count": len(records), "source": "gtfs_tam",
                "routes": [dict(r) for r in records]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- DEMOGRAPHICS --------------------------------------------------------------

@app.get("/demographics", tags=["Demographics"])
def get_demographics():
    """
    INSEE RP 2020 commune-level demographic data for
    Montpellier Mediterranee Metropole (31 communes).
    """
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT codgeo, population,
                   pct_high_income, pct_low_income,
                   pct_65plus, pct_young_adult, pct_youth,
                   pct_cadres, pct_employes, pct_ouvriers, pct_retraites,
                   updated_at
            FROM public.dim_communes_demographics
            ORDER BY population DESC
        """)
        records = cur.fetchall()
        cur.close(); con.close()
        data = [dict(r) for r in records]
        for r in data:
            if r.get("updated_at"):
                r["updated_at"] = str(r["updated_at"])
        return {"count": len(data), "source": "insee_rp_2020", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- FAIRNESS ------------------------------------------------------------------

@app.get("/fairness", tags=["Fairness"])
def get_fairness():
    """
    Spatial fairness analysis — station distribution by zone
    (centre / intermediaire / peripherique) with demographic context.

    Uses v_station_fairness view built from dim_stations + dim_communes_demographics.
    No personal data — aggregate station-level analysis only (RGPD compliant).
    """
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Zone-level summary
        cur.execute("""
            SELECT
                zone,
                COUNT(*)                     AS n_stations,
                ROUND(AVG(dist_centre_km)::numeric, 2) AS avg_dist_km,
                ROUND(AVG(pct_high_income)::numeric, 1) AS avg_pct_high_income,
                ROUND(AVG(pct_65plus)::numeric, 1)      AS avg_pct_65plus,
                ROUND(AVG(pct_young_adult)::numeric, 1) AS avg_pct_young_adult
            FROM public.v_station_fairness
            GROUP BY zone
            ORDER BY avg_dist_km
        """)
        zones = [dict(r) for r in cur.fetchall()]

        # Station-level detail
        cur.execute("""
            SELECT station_id, nom, lat, lon, zone,
                   dist_centre_km, pct_high_income, pct_65plus, pct_young_adult
            FROM public.v_station_fairness
            ORDER BY dist_centre_km
        """)
        stations = [dict(r) for r in cur.fetchall()]

        cur.close(); con.close()

        return {
            "zone_summary": zones,
            "stations":     stations,
            "note":         "Aggregate station-level analysis only — no personal data (RGPD compliant)",
            "timestamp":    datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -- JOURNEY PLANNER ----------------------------------------------------------

@app.post("/journey", tags=["Journey"])
def compute_journey(req: JourneyRequest):
    """
    Multimodal journey planner — A to B.

    Returns options for velo, tram, bus, marche, voiture ranked by CO2.
    Includes ML bike availability prediction, time until next available bike,
    nearest TAM stop with next departure, and weather/AQI impact.
    """
    now          = datetime.now()
    heure        = req.heure        if req.heure        is not None else now.hour
    jour_semaine = req.jour_semaine if req.jour_semaine is not None else now.weekday()
    mois         = req.mois         if req.mois         is not None else now.month
    jour_mois    = req.jour_mois    if req.jour_mois    is not None else now.day
    precipitation = req.precipitation or 0.0
    temperature   = req.temperature  or 20.0
    aqi           = req.indice_qualite or 3

    # 1. Haversine distance A -> B
    dlat = math.radians(req.lat_b - req.lat_a)
    dlon = math.radians(req.lon_b - req.lon_a)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(req.lat_a)) *
         math.cos(math.radians(req.lat_b)) *
         math.sin(dlon/2)**2)
    distance_km = round(6371 * 2 * math.asin(math.sqrt(a)), 2)

    # 2. Base route options
    co2_factors = {"velo": 0, "tram": 4, "bus": 68, "voiture": 120, "marche": 0}
    speeds      = {"velo": 15, "tram": 25, "bus": 20, "voiture": 30, "marche": 5}

    routes = {}
    for mode, co2_per_km in co2_factors.items():
        duration_min     = round(distance_km / speeds[mode] * 60, 1)
        co2_total_g      = round(distance_km * co2_per_km, 1)
        co2_saved_vs_car = round(distance_km * co2_factors["voiture"] - co2_total_g, 1)
        routes[mode] = {
            "mode":             mode,
            "distance_km":      distance_km,
            "duration_min":     duration_min,
            "co2_g":            co2_total_g,
            "co2_saved_vs_car": co2_saved_vs_car,
            "recommended":      False,
            "score":            co2_total_g,
            "warnings":         [],
            "details":          {}
        }

    # 3. ML bike availability + nearest station
    bike_info = {
        "available": False, "station_id": None, "predicted_bikes": 0,
        "minutes_until_available": None, "station_nom": None,
        "dist_to_station_km": None
    }

    if ml_model is not None:
        try:
            con = get_pg()
            cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT station_id, nom, lat, lon, capacite,
                    SQRT(POWER((lat - %s)*111,2) + POWER((lon - %s)*85,2)) AS dist_km,
                    SQRT(POWER((lat - 43.6109)*111,2) + POWER((lon - 3.8763)*85,2)) AS dist_centre_km
                FROM public.dim_stations
                WHERE type = 'velomagg'
                ORDER BY dist_km LIMIT 1
            """, (req.lat_a, req.lon_a))
            station = cur.fetchone()
            cur.close(); con.close()

            if station:
                try:
                    station_enc = ml_encoder.transform([station["station_id"]])[0]
                except Exception:
                    station_enc = 0

                def predict_bikes(h):
                    row = {
                        "heure": h, "jour_semaine": jour_semaine,
                        "mois": mois, "jour_mois": jour_mois,
                        "heure_pointe": 1 if (7<=h<=9 or 17<=h<=19) else 0,
                        "weekend": 1 if jour_semaine >= 5 else 0,
                        "lat": float(station["lat"]), "lon": float(station["lon"]),
                        "capacite": float(station["capacite"]),
                        "dist_centre_km": float(station["dist_centre_km"]),
                        "station_encoded": station_enc,
                        "temperature_max": temperature,
                        "precipitation_sum": precipitation,
                        "wind_speed_max": req.wind_speed or 10.0,
                        "indice_qualite": aqi,
                        "no2": 10, "o3": 50, "pm10": 15,
                        "pct_young_adult": 31.20, "pct_active": 38.05,
                        "pct_65plus": 18.85, "pct_high_income": 12.79,
                        "pct_low_income": 22.46, "population": 299096,
                    }
                    X = pd.DataFrame([row])[ml_features].fillna(0)
                    return max(0, round(float(ml_model.predict(X)[0]), 1))

                predicted_now = predict_bikes(heure)
                bike_info["station_id"]        = station["station_id"]
                bike_info["station_nom"]        = station["nom"]
                bike_info["predicted_bikes"]    = predicted_now
                bike_info["dist_to_station_km"] = round(float(station["dist_km"]), 2)
                bike_info["available"]          = predicted_now >= 1

                # Time until next bike available
                if predicted_now < 1:
                    for delta_min in [30, 60, 90, 120]:
                        future_h    = (heure + delta_min // 60) % 24
                        future_pred = predict_bikes(future_h)
                        if future_pred >= 1:
                            bike_info["minutes_until_available"] = delta_min
                            break

        except Exception as e:
            bike_info["error"] = str(e)

    routes["velo"]["details"]["bike_prediction"] = bike_info

    # 4. AQI and weather scoring adjustments
    if precipitation > 5:
        routes["velo"]["score"]   += 50
        routes["marche"]["score"] += 30
        routes["velo"]["warnings"].append("Rain expected — cycling may be uncomfortable")
        routes["marche"]["warnings"].append("Rain expected")

    if aqi >= 4:
        routes["velo"]["score"]   += 40
        routes["marche"]["score"] += 40
        routes["velo"]["warnings"].append(f"Poor air quality (AQI={aqi}) — not recommended for sensitive groups")
        routes["marche"]["warnings"].append(f"Poor air quality (AQI={aqi})")

    if distance_km > 5:
        routes["marche"]["score"] += 200
        routes["marche"]["warnings"].append("Distance too long for walking (>5km)")

    if not bike_info["available"]:
        routes["velo"]["score"] += 100
        if bike_info.get("minutes_until_available"):
            routes["velo"]["warnings"].append(
                f"No bikes available now — next bike in ~{bike_info['minutes_until_available']} min"
            )
        else:
            routes["velo"]["warnings"].append("No bikes predicted at nearest station")

    # 5. Nearest TAM stop + next departures
    tam_info = {"stop_name": None, "dist_km": None, "next_departures": []}
    try:
        con = get_pg()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT stop_id, stop_name, stop_lat, stop_lon,
                SQRT(POWER((stop_lat - %s)*111,2) + POWER((stop_lon - %s)*85,2)) AS dist_km
            FROM public.dim_tam_stops
            WHERE stop_lat IS NOT NULL
            ORDER BY dist_km LIMIT 1
        """, (req.lat_a, req.lon_a))
        nearest_stop = cur.fetchone()

        if nearest_stop:
            tam_info["stop_name"] = nearest_stop["stop_name"]
            tam_info["dist_km"]   = round(float(nearest_stop["dist_km"]), 2)
            tam_info["stop_id"]   = str(nearest_stop["stop_id"])

            current_time = f"{heure:02d}:{now.minute:02d}:00"
            cur.execute("""
                SELECT st.departure_time, r.route_name, r.route_color, t.trip_headsign
                FROM public.dim_tam_stop_times st
                JOIN public.dim_tam_trips  t ON st.trip_id = t.trip_id
                JOIN public.dim_tam_routes r ON t.route_id = r.route_id
                WHERE st.stop_id = %s
                  AND st.departure_time >= %s
                ORDER BY st.departure_time
                LIMIT 5
            """, (str(nearest_stop["stop_id"]), current_time))
            tam_info["next_departures"] = [dict(d) for d in cur.fetchall()]

        cur.close(); con.close()
    except Exception as e:
        tam_info["error"] = str(e)

    routes["tram"]["details"]["tam"] = tam_info
    routes["bus"]["details"]["tam"]  = tam_info

    # 6. Final ranking + recommendation
    sorted_routes = sorted(routes.values(), key=lambda x: x["score"])
    sorted_routes[0]["recommended"] = True
    best_mode = sorted_routes[0]["mode"]

    co2_saved = routes[best_mode]["co2_saved_vs_car"]

    return {
        "distance_km": distance_km,
        "best_mode":   best_mode,
        "routes":      sorted_routes,
        "conditions": {
            "hour":         heure,
            "day_of_week":  jour_semaine,
            "is_peak_hour": bool(7 <= heure <= 9 or 17 <= heure <= 19),
            "is_weekend":   bool(jour_semaine >= 5),
            "precipitation": precipitation,
            "temperature":  temperature,
            "aqi":          aqi,
        },
        "carbon_passport": {
            "co2_saved_vs_car_g": co2_saved,
            "trees_equivalent":   round(co2_saved / 22000, 4) if co2_saved > 0 else 0,
            "best_mode_co2_g":    routes[best_mode]["co2_g"],
        },
        "timestamp": datetime.now().isoformat()
    }


# --- MAIN ---------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)

# =============================================================================
# LILLE ENDPOINTS
# =============================================================================

@app.get("/lille/stations")
def get_lille_stations():
    """V'Lille stations — temps réel"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT station_id, nom, adresse, commune, code_insee,
                   etat, type, nb_velos_dispo, nb_places_dispo,
                   etat_connexion, lon, lat
            FROM lille.dim_vlille_stations
            ORDER BY nom
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "stations": rows}
    except Exception as e:
        return {"error": str(e)}


@app.get("/lille/parkings")
def get_lille_parkings():
    """Parkings MEL — temps réel"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT parking_id, nom, adresse, ville, etat,
                   nb_total, nb_libre, taux_occupation, lon, lat
            FROM lille.dim_parkings
            ORDER BY nom
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "parkings": rows}
    except Exception as e:
        return {"error": str(e)}


@app.get("/lille/arrets")
def get_lille_arrets():
    """ilévia — arrêts bus/métro/tram"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT stop_id, stop_name, commune, lon, lat
            FROM lille.dim_arrets
            ORDER BY stop_name
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "arrets": rows}
    except Exception as e:
        return {"error": str(e)}


@app.get("/lille/aqi")
def get_lille_aqi():
    """Qualité de l'air — Atmo Hauts-de-France"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT lib_zone, date_ech, code_qual, lib_qual,
                   code_no2, code_o3, code_pm10, lon, lat
            FROM lille.dim_qualite_air
            WHERE date_ech = (SELECT MAX(date_ech) FROM lille.dim_qualite_air)
              AND lib_zone ILIKE '%lille%'
            ORDER BY lib_zone
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "aqi": rows}
    except Exception as e:
        return {"error": str(e)}


@app.get("/lille/meteo")
def get_lille_meteo():
    """Météo 7 jours — Lille"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT date, temperature_max, temperature_min,
                   precipitation_sum, wind_speed_max, weather_code
            FROM lille.dim_meteo
            ORDER BY date
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "meteo": rows}
    except Exception as e:
        return {"error": str(e)}


@app.get("/lille/demographics")
def get_lille_demographics():
    """Démographie MEL — INSEE RP 2020"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT codgeo, population, pct_young_adult, pct_active,
                   pct_65plus, pct_high_income, pct_low_income
            FROM lille.dim_demographics
            ORDER BY population DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "demographics": rows}
    except Exception as e:
        return {"error": str(e)}


@app.get("/imd")
def get_imd():
    """Indice de Mobilité Durable — Montpellier & Lille"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT ville, imd_score, score_marche, score_velo, score_transport,
                   score_mix_usage, score_densite, score_compacite,
                   score_connectivite, score_environnement, computed_at
            FROM public.dim_imd_scores
            ORDER BY imd_score DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "imd": rows}
    except Exception as e:
        return {"error": str(e)}

# =============================================================================
# LILLE ENDPOINTS
# =============================================================================

@app.get("/lille/stations")
def get_lille_stations():
    """V'Lille stations — temps réel"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT station_id, nom, adresse, commune, code_insee,
                   etat, type, nb_velos_dispo, nb_places_dispo,
                   etat_connexion, lon, lat, date_modification
            FROM lille.dim_vlille_stations
            ORDER BY nom
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "stations": rows}
    except Exception as e:
        return {"error": str(e)}

@app.get("/lille/parkings")
def get_lille_parkings():
    """Parkings MEL — temps réel"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT parking_id, nom, adresse, ville, code_insee,
                   etat, nb_total, nb_libre, taux_occupation, lon, lat, timestamp
            FROM lille.dim_parkings
            ORDER BY nom
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "parkings": rows}
    except Exception as e:
        return {"error": str(e)}

@app.get("/lille/arrets")
def get_lille_arrets():
    """ilévia — arrêts bus/métro/tram"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT stop_id, stop_name, stop_desc, commune, lon, lat
            FROM lille.dim_arrets
            ORDER BY stop_name
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "arrets": rows}
    except Exception as e:
        return {"error": str(e)}

@app.get("/lille/aqi")
def get_lille_aqi():
    """Qualité de l'air — Atmo Hauts-de-France"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT lib_zone, date_ech, code_qual, lib_qual,
                   code_no2, code_o3, code_pm10, lon, lat
            FROM lille.dim_qualite_air
            WHERE date_ech = (SELECT MAX(date_ech) FROM lille.dim_qualite_air)
            ORDER BY lib_zone
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "aqi": rows}
    except Exception as e:
        return {"error": str(e)}

@app.get("/lille/meteo")
def get_lille_meteo():
    """Météo 7 jours — Lille (Open-Meteo)"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT date, temperature_max, temperature_min,
                   precipitation_sum, wind_speed_max, weather_code
            FROM lille.dim_meteo
            ORDER BY date
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "meteo": rows}
    except Exception as e:
        return {"error": str(e)}

@app.get("/lille/demographics")
def get_lille_demographics():
    """Démographie MEL — INSEE RP 2020"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT codgeo, population, pct_young_adult, pct_active,
                   pct_65plus, pct_high_income, pct_low_income
            FROM lille.dim_demographics
            ORDER BY population DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "demographics": rows}
    except Exception as e:
        return {"error": str(e)}

@app.get("/lille/bike-histo")
def get_lille_bike_histo():
    """Comptages vélos historiques — Lille (2013+)"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT compteur_id, nom, ville, code_insee,
                   annee, semaine, mjo, lon, lat
            FROM lille.dim_bike_histo
            ORDER BY annee DESC, semaine DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "bike_histo": rows}
    except Exception as e:
        return {"error": str(e)}

@app.get("/lille/emprunts/stats")
def get_lille_emprunts_stats():
    """Emprunts V'Lille — statistiques agrégées par station"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id_station_depart as station_id,
                   nom_station_depart as nom,
                   commune_depart as commune,
                   COUNT(*) as nb_emprunts,
                   COUNT(DISTINCT DATE(date_debut)) as nb_jours_actifs
            FROM lille.dim_emprunt_vlille
            GROUP BY id_station_depart, nom_station_depart, commune_depart
            ORDER BY nb_emprunts DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "emprunts_stats": rows}
    except Exception as e:
        return {"error": str(e)}

@app.get("/lille/emprunts/communes")
def get_lille_emprunts_communes():
    """Emprunts V'Lille — agrégés par commune"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT commune_depart as commune,
                   COUNT(*) as nb_emprunts,
                   COUNT(DISTINCT id_station_depart) as nb_stations
            FROM lille.dim_emprunt_vlille
            GROUP BY commune_depart
            ORDER BY nb_emprunts DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "emprunts_communes": rows}
    except Exception as e:
        return {"error": str(e)}

@app.get("/imd")
def get_imd():
    """Indice de Mobilité Durable — Montpellier & Lille"""
    try:
        conn = get_pg()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT ville, imd_score,
                   score_marche, score_velo, score_transport,
                   score_mix_usage, score_densite, score_compacite,
                   score_connectivite, score_environnement,
                   computed_at
            FROM public.dim_imd_scores
            ORDER BY imd_score DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()
        return {"total": len(rows), "imd": rows}
    except Exception as e:
        return {"error": str(e)}
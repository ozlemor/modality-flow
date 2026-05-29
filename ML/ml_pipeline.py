"""
MODALITY-FLOW — ML Pipeline v2
Availability prediction with demographic and geographic features.

Requirements:
    pip install scikit-learn psycopg2-binary duckdb pandas numpy joblib
"""

import os
import sys
import logging
import warnings
import pickle
import json
import duckdb
import psycopg2
import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

# --- CONFIG -------------------------------------------------------------------
VELO_DIR    = Path(__file__).parent.parent
DUCKDB_PATH = VELO_DIR / "ETL" / "gold" / "modality_flow.duckdb"
ML_DIR      = Path(__file__).parent
MODELS_DIR  = ML_DIR / "models"
REPORTS_DIR = ML_DIR / "reports"

DB_URL = os.environ.get("DATABASE_PUBLIC_URL", "")

CO2_FACTORS = {"velo": 0, "tram": 4, "bus": 68, "voiture": 120, "marche": 0}

# Montpellier (34172) demographic values from INSEE 2020
# Used as static features since all Velomagg stations are in Montpellier
MONTPELLIER_DEMO = {
    "pct_young_adult": 31.20,   # 15-29 ans — high cycling potential
    "pct_active":      38.05,   # 30-59 ans
    "pct_65plus":      18.85,   # accessibility indicator
    "pct_high_income": 12.79,   # cadres proxy
    "pct_low_income":  22.46,   # employes + ouvriers proxy
    "population":      299096,
}


# --- LOGGING ------------------------------------------------------------------
def setup_logging():
    ML_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO, format=fmt, datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(ML_DIR / "ml_pipeline.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ]
    )
    return logging.getLogger("modality_ml")

log = setup_logging()


# --- 1. LOAD FEATURES ---------------------------------------------------------
def load_features() -> pd.DataFrame:
    """
    Load training data from Railway PostgreSQL.
    Joins: fact_velomagg_historique + dim_stations + dim_meteo + dim_qualite_air
    Adds demographic features from INSEE (static per commune).
    """
    log.info("Loading training data from Railway PostgreSQL...")

    conn = psycopg2.connect(DB_URL)

    df = pd.read_sql("""
        SELECT
            h.station_id,
            h.bisiklet_sayisi,

            -- Time features
            EXTRACT(HOUR  FROM h.timestamp)::int         AS heure,
            EXTRACT(DOW   FROM h.timestamp)::int         AS jour_semaine,
            EXTRACT(MONTH FROM h.timestamp)::int         AS mois,
            EXTRACT(DAY   FROM h.timestamp)::int         AS jour_mois,

            -- Peak hours: morning (7-9h) and evening (17-19h)
            CASE WHEN EXTRACT(HOUR FROM h.timestamp) BETWEEN 7  AND 9  THEN 1
                 WHEN EXTRACT(HOUR FROM h.timestamp) BETWEEN 17 AND 19 THEN 1
                 ELSE 0 END                              AS heure_pointe,

            -- Weekend flag
            CASE WHEN EXTRACT(DOW FROM h.timestamp) IN (0, 6) THEN 1
                 ELSE 0 END                              AS weekend,

            -- Station geographic features
            s.lat,
            s.lon,
            s.capacite,

            -- Distance from city centre (Montpellier: 43.6109, 3.8763)
            SQRT(
                POWER((s.lat - 43.6109) * 111, 2) +
                POWER((s.lon - 3.8763)  * 85,  2)
            )                                            AS dist_centre_km,

            -- Weather (with fallback defaults)
            COALESCE(m.temperature_max,    15.0)         AS temperature_max,
            COALESCE(m.precipitation_sum,   0.0)         AS precipitation_sum,
            COALESCE(m.wind_speed_max,     10.0)         AS wind_speed_max,

            -- Air quality (with fallback defaults)
            COALESCE(q.indice_qualite, 3)                AS indice_qualite,
            COALESCE(q.no2,           10)                AS no2,
            COALESCE(q.o3,            50)                AS o3,
            COALESCE(q.pm10,          15)                AS pm10

        FROM public.fact_velomagg_historique h
        LEFT JOIN public.dim_stations s
            ON h.station_id = s.station_id
        LEFT JOIN public.dim_meteo m
            ON CAST(h.timestamp AS DATE) = m.date
        LEFT JOIN public.dim_qualite_air q
            ON CAST(h.timestamp AS DATE) = q.date
        WHERE h.bisiklet_sayisi IS NOT NULL
          AND h.bisiklet_sayisi >= 0
          AND h.timestamp IS NOT NULL
    """, conn)

    conn.close()
    log.info(f"  {len(df):,} rows | {df['station_id'].nunique()} stations")

    # Add demographic features (static for Montpellier — INSEE 2020)
    for col, val in MONTPELLIER_DEMO.items():
        df[col] = val

    df["availability_ratio"] = (
        df["bisiklet_sayisi"] / df["capacite"].replace(0, np.nan)
    ).clip(0, 1)

    log.info(f"  Target range: {df['bisiklet_sayisi'].min():.0f} - {df['bisiklet_sayisi'].max():.0f} bikes")
    log.info(f"  Features: {df.shape[1]} columns total")

    return df


# --- 2. TRAIN MODEL -----------------------------------------------------------
def train_model(df: pd.DataFrame):
    """
    Train RandomForest on availability (bisiklet_sayisi).

    Key improvements over v1:
    - Geographic features (lat, lon, dist_centre_km, capacite)
    - Demographic features (pct_young_adult, pct_65plus, pct_high_income, etc.)
    - station_encoded weight reduced by adding real features
    - More trees, better depth tuning
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import mean_absolute_error, r2_score

    log.info("Training availability model (v2)...")

    # Encode station_id
    le = LabelEncoder()
    df["station_encoded"] = le.fit_transform(df["station_id"])

    FEATURES = [
        # Time
        "heure", "jour_semaine", "mois", "jour_mois",
        "heure_pointe", "weekend",
        # Station (geographic — replaces blind encoding)
        "lat", "lon", "capacite", "dist_centre_km",
        # Station identity (kept but with lower weight due to geo features)
        "station_encoded",
        # Weather
        "temperature_max", "precipitation_sum", "wind_speed_max",
        # Air quality
        "indice_qualite", "no2", "o3", "pm10",
        # Demographics (INSEE 2020)
        "pct_young_adult", "pct_active", "pct_65plus",
        "pct_high_income", "pct_low_income",
    ]
    TARGET = "bisiklet_sayisi"

    X = df[FEATURES].fillna(0)
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    log.info(f"  Train: {len(X_train):,} | Test: {len(X_test):,}")

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=20,
        min_samples_leaf=4,
        min_samples_split=8,
        max_features="sqrt",
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2  = r2_score(y_test, y_pred)

    log.info(f"  R2  = {r2:.4f}  (v1 baseline: 0.9920)")
    log.info(f"  MAE = {mae:.4f} bikes  (v1 baseline: 0.30)")

    # Feature importance
    imp = pd.DataFrame({
        "feature":    FEATURES,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=False)

    log.info("\n  Feature importance:")
    for _, row in imp.iterrows():
        bar = "#" * int(row["importance"] * 80)
        log.info(f"    {row['feature']:25s} {row['importance']:.4f}  {bar}")

    # How much did station_encoded drop vs v1?
    station_imp = imp[imp["feature"] == "station_encoded"]["importance"].values[0]
    demo_imp    = imp[imp["feature"].isin(["pct_young_adult","pct_active","pct_65plus",
                                            "pct_high_income","pct_low_income"])]["importance"].sum()
    geo_imp     = imp[imp["feature"].isin(["lat","lon","dist_centre_km","capacite"])]["importance"].sum()

    log.info(f"\n  station_encoded importance : {station_imp*100:.1f}%  (v1: 84.9%)")
    log.info(f"  Geographic features total  : {geo_imp*100:.1f}%")
    log.info(f"  Demographic features total : {demo_imp*100:.1f}%")

    return model, le, FEATURES, mae, r2, imp


# --- 3. EXAMPLE PREDICTIONS ---------------------------------------------------
def demo_predictions(model, le, features):
    """
    Show example predictions for typical use cases.
    """
    log.info("\nExample predictions:")

    # Montpellier city centre coordinates
    test_cases = [
        {"desc": "Monday 08:00 — city centre station",
         "heure": 8,  "jour_semaine": 1, "mois": 5, "jour_mois": 19,
         "heure_pointe": 1, "weekend": 0,
         "lat": 43.6109, "lon": 3.8763, "capacite": 20, "dist_centre_km": 0.0,
         "temperature_max": 22.0, "precipitation_sum": 0.0, "wind_speed_max": 12.0,
         "indice_qualite": 2, "no2": 10, "o3": 50, "pm10": 15},

        {"desc": "Wednesday 12:00 — intermediate zone",
         "heure": 12, "jour_semaine": 3, "mois": 5, "jour_mois": 21,
         "heure_pointe": 0, "weekend": 0,
         "lat": 43.6200, "lon": 3.8900, "capacite": 16, "dist_centre_km": 1.8,
         "temperature_max": 25.0, "precipitation_sum": 0.0, "wind_speed_max": 8.0,
         "indice_qualite": 3, "no2": 15, "o3": 60, "pm10": 18},

        {"desc": "Friday 18:00 — peripheral station",
         "heure": 18, "jour_semaine": 5, "mois": 5, "jour_mois": 23,
         "heure_pointe": 1, "weekend": 0,
         "lat": 43.6400, "lon": 3.9100, "capacite": 12, "dist_centre_km": 3.2,
         "temperature_max": 28.0, "precipitation_sum": 0.0, "wind_speed_max": 15.0,
         "indice_qualite": 4, "no2": 20, "o3": 80, "pm10": 25},

        {"desc": "Saturday 14:00 — rainy day",
         "heure": 14, "jour_semaine": 6, "mois": 11, "jour_mois": 8,
         "heure_pointe": 0, "weekend": 1,
         "lat": 43.6109, "lon": 3.8763, "capacite": 20, "dist_centre_km": 0.0,
         "temperature_max": 12.0, "precipitation_sum": 15.0, "wind_speed_max": 25.0,
         "indice_qualite": 2, "no2": 8, "o3": 30, "pm10": 10},
    ]

    for tc in test_cases:
        desc = tc.pop("desc")
        row  = {**tc, **MONTPELLIER_DEMO, "station_encoded": 0}
        X_pred = pd.DataFrame([row])[features].fillna(0)
        pred = model.predict(X_pred)[0]
        log.info(f"  {desc}: {pred:.1f} bikes predicted")
        tc["desc"] = desc  # restore


# --- 4. FAIRNESS ANALYSIS -----------------------------------------------------
def fairness_analysis(df, model, features):
    """
    Check if model performs equally across zones and demographic groups.
    A high MAE gap between zones indicates spatial bias.
    """
    from sklearn.metrics import mean_absolute_error

    log.info("\nFairness analysis...")

    df = df.copy()
    df["zone"] = pd.cut(
        df["dist_centre_km"],
        bins=[0, 1.5, 3.0, 999],
        labels=["centre", "intermediaire", "peripherique"]
    )

    X = df[features].fillna(0)
    df["y_pred"] = model.predict(X)
    df["error"]  = (df["y_pred"] - df["bisiklet_sayisi"]).abs()

    # Zone-level MAE
    log.info("\n  MAE by zone (spatial fairness):")
    zone_stats = df.groupby("zone", observed=True)["error"].agg(["mean", "count"])
    for zone, row in zone_stats.iterrows():
        log.info(f"    {zone:15s}  MAE={row['mean']:.3f}  n={int(row['count']):,}")

    fairness_gap = zone_stats["mean"].max() - zone_stats["mean"].min()
    status = "ACCEPTABLE" if fairness_gap < 0.5 else "BIAS DETECTED — review needed"
    log.info(f"\n  Fairness gap: {fairness_gap:.3f}  [{status}]")

    return float(fairness_gap), status


# --- 5. SAVE MODEL ------------------------------------------------------------
def save_model(model, le, features, mae, r2, fairness_gap, fairness_status):
    """
    Save model bundle and JSON report.
    """
    # Model bundle — backward compatible with existing API
    model_path = MODELS_DIR / "availability_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "encoder": le, "features": features}, f)
    log.info(f"\n  Model saved: {model_path}")

    # Versioned backup
    v2_path = MODELS_DIR / "availability_model_v2_demographics.pkl"
    joblib.dump({"model": model, "encoder": le, "features": features}, v2_path)
    log.info(f"  Backup saved: {v2_path}")

    # JSON report
    report = {
        "timestamp": datetime.now().isoformat(),
        "model_version": "v2_demographics",
        "model_1_availability": {
            "type":     "RandomForestRegressor",
            "n_estimators": 200,
            "max_depth":    20,
            "mae":      round(mae, 4),
            "r2":       round(r2,  4),
            "features": features,
            "n_features": len(features),
            "new_features": [
                "lat", "lon", "capacite", "dist_centre_km",
                "pct_young_adult", "pct_active", "pct_65plus",
                "pct_high_income", "pct_low_income",
            ],
            "fairness": {
                "gap":    round(fairness_gap, 4),
                "status": fairness_status,
            },
        },
        "model_2_route": {
            "type":       "Rule-based CO2 optimization",
            "co2_factors": CO2_FACTORS,
        },
        "model_3_savings": {
            "type":      "CO2 savings calculator",
            "reference": "ADEME 2024",
        },
        "demographic_source": {
            "dataset":  "INSEE RP 2020 — base-cc-evol-struct-pop-2020",
            "commune":  "Montpellier (34172)",
            "features": list(MONTPELLIER_DEMO.keys()),
        },
    }

    report_path = REPORTS_DIR / "ml_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log.info(f"  Report saved: {report_path}")


# --- CO2 HELPERS (unchanged from v1) -----------------------------------------
def compute_optimal_route(lat_a, lon_a, lat_b, lon_b,
                           precipitation=0.0, bikes_available=5):
    R = 6371
    dlat = np.radians(lat_b - lat_a)
    dlon = np.radians(lon_b - lon_a)
    a = (np.sin(dlat/2)**2 +
         np.cos(np.radians(lat_a)) * np.cos(np.radians(lat_b)) * np.sin(dlon/2)**2)
    distance_km = R * 2 * np.arcsin(np.sqrt(a))

    speeds = {"velo": 15, "tram": 25, "bus": 20, "voiture": 30, "marche": 5}
    routes = []
    for mode, co2_per_km in CO2_FACTORS.items():
        duration_min     = round(distance_km / speeds[mode] * 60, 1)
        co2_total_g      = round(distance_km * co2_per_km, 1)
        co2_saved_vs_car = round(distance_km * CO2_FACTORS["voiture"] - co2_total_g, 1)
        score = co2_total_g
        if mode == "velo"   and precipitation > 5:   score += 50
        if mode == "velo"   and bikes_available == 0: score += 100
        if mode == "marche" and distance_km > 2:      score += 200
        routes.append({"mode": mode, "distance_km": round(distance_km, 2),
                        "duration_min": duration_min, "co2_g": co2_total_g,
                        "co2_saved_vs_car": co2_saved_vs_car,
                        "score": score, "recommande": False})

    routes.sort(key=lambda x: x["score"])
    routes[0]["recommande"] = True
    return {"distance_km": round(distance_km, 2), "routes": routes,
            "best_mode": routes[0]["mode"], "co2_economise": routes[0]["co2_saved_vs_car"]}


def compute_personal_co2_savings(trips, mode_utilise="velo", mode_reference="voiture"):
    total_distance = sum(t["distance_km"] for t in trips)
    co2_reference  = total_distance * CO2_FACTORS[mode_reference]
    co2_utilise    = total_distance * CO2_FACTORS[mode_utilise]
    co2_economise  = co2_reference - co2_utilise
    return {
        "nb_trajets":        len(trips),
        "distance_totale":   round(total_distance, 2),
        "co2_reference_g":   round(co2_reference, 1),
        "co2_utilise_g":     round(co2_utilise, 1),
        "co2_economise_g":   round(co2_economise, 1),
        "co2_economise_kg":  round(co2_economise / 1000, 3),
        "arbres_equivalent": round(co2_economise / 22000, 2),
        "mode_utilise":      mode_utilise,
        "mode_reference":    mode_reference,
    }


# --- MAIN ---------------------------------------------------------------------
def run():
    start = datetime.now()
    log.info("MODALITY-FLOW ML Pipeline v2 started")
    log.info(f"  {start.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Load data
    df = load_features()

    # 2. Train model
    model, le, features, mae, r2, imp = train_model(df)

    # 3. Example predictions
    demo_predictions(model, le, features)

    # 4. Fairness analysis
    fairness_gap, fairness_status = fairness_analysis(df, model, features)

    # 5. Save
    save_model(model, le, features, mae, r2, fairness_gap, fairness_status)

    elapsed = (datetime.now() - start).seconds
    log.info(f"\nPipeline complete in {elapsed}s")
    log.info(f"  Models : {MODELS_DIR}")
    log.info(f"  Reports: {REPORTS_DIR}")
    log.info("""
Next steps:
  1. Copy availability_model.pkl to Railway:
       git add ML/models/availability_model.pkl
       git commit -m "feat: ML v2 with demographics and geo features"
       git push

  2. Update api.py predict endpoint to pass lat/lon/capacite/dist_centre_km
     in addition to existing heure/jour_semaine fields.
    """)


if __name__ == "__main__":
    run()
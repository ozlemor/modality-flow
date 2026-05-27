"""
MODALITY-FLOW — Indice de Mobilité Durable (IMD)
Méthodologie : ITDP + Méthode suédoise
Villes : Montpellier & Lille
Score : 0 à 100

Dimensions (8 — adapté ITDP) :
  1. Marche          — accessibilité piétonne
  2. Vélo            — disponibilité & usage vélos
  3. Transport       — offre transport collectif
  4. Mix usage       — multimodalité
  5. Densité         — densité population
  6. Compacité       — concentration services mobilité
  7. Connectivité    — connexions intermodales
  8. Environnement   — qualité air & CO2

Usage:
    cd ~/Desktop/Velo
    python3 indice_mobilite.py
"""

import pandas as pd
import numpy as np
import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values
import json
from datetime import datetime

DB_URL = "postgresql://postgres:PfbeGtHyxglIyRBZppgxBxPtYMQUmoyy@gondola.proxy.rlwy.net:46226/railway"

def get_pg():
    return psycopg2.connect(DB_URL)

def normalize(value, min_val, max_val, inverse=False):
    """Normalize value to 0-100 scale."""
    if max_val == min_val:
        return 50.0
    score = (value - min_val) / (max_val - min_val) * 100
    score = max(0, min(100, score))
    return 100 - score if inverse else score


# =============================================================================
# MONTPELLIER INDICATORS
# =============================================================================

def get_montpellier_indicators(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    indicators = {}

    # 1. Vélo — stations & disponibilité
    cur.execute("""
        SELECT
            COUNT(*) as nb_stations,
            AVG(capacite) as avg_capacite,
            SUM(capacite) as total_capacite
        FROM public.dim_stations
        WHERE type = 'velomagg'
    """)
    velo = cur.fetchone()
    indicators["nb_stations_velo"]  = float(velo["nb_stations"])
    indicators["total_capacite"]    = float(velo["total_capacite"] or 0)
    indicators["avg_capacite"]      = float(velo["avg_capacite"] or 0)

    # 2. Vélo — free bikes
    cur.execute("SELECT COUNT(*) as nb FROM modality.fact_free_bikes WHERE is_disabled = false")
    fb = cur.fetchone()
    indicators["nb_free_bikes"] = float(fb["nb"])

    # 3. Transport collectif — arrêts TAM
    cur.execute("SELECT COUNT(*) as nb FROM public.dim_tam_stops")
    tc = cur.fetchone()
    indicators["nb_arrets_tc"] = float(tc["nb"])

    # 4. Transport — lignes
    cur.execute("SELECT COUNT(*) as nb FROM public.dim_tam_routes")
    lig = cur.fetchone()
    indicators["nb_lignes"] = float(lig["nb"])

    # 5. Parkings
    cur.execute("""
        SELECT COUNT(*) as nb, AVG(taux_occupation) as avg_occ
        FROM (
            SELECT DISTINCT ON (parking_id) parking_id, taux_occupation, timestamp
            FROM modality.fact_parkings_status
            ORDER BY parking_id, timestamp DESC
        ) latest
    """)
    pk = cur.fetchone()
    indicators["nb_parkings"]          = float(pk["nb"] or 0)
    indicators["taux_occupation_moy"]  = float(pk["avg_occ"] or 50)

    # 6. Qualité air
    cur.execute("""
        SELECT indice_qualite, no2, o3, pm10
        FROM public.dim_qualite_air
        ORDER BY date DESC LIMIT 1
    """)
    aqi = cur.fetchone()
    if aqi:
        indicators["indice_qualite"] = float(aqi["indice_qualite"] or 3)
        indicators["no2"]  = float(aqi["no2"]  or 10)
        indicators["o3"]   = float(aqi["o3"]   or 50)
        indicators["pm10"] = float(aqi["pm10"] or 15)
    else:
        indicators["indice_qualite"] = 3.0
        indicators["no2"] = 10.0
        indicators["o3"]  = 50.0
        indicators["pm10"] = 15.0

    # 7. Démographie
    cur.execute("""
        SELECT AVG(population) as pop, AVG(pct_young_adult) as young,
               AVG(pct_65plus) as senior, AVG(pct_high_income) as rich
        FROM public.dim_communes_demographics
    """)
    dem = cur.fetchone()
    indicators["population_moy"]    = float(dem["pop"]    or 0)
    indicators["pct_young_adult"]   = float(dem["young"]  or 0)
    indicators["pct_65plus"]        = float(dem["senior"] or 0)
    indicators["pct_high_income"]   = float(dem["rich"]   or 0)

    # 8. Fairness
    cur.execute("""
        SELECT zone, COUNT(*) as nb_stations
        FROM public.v_station_fairness
        GROUP BY zone
    """)
    zones = {r["zone"]: r["nb_stations"] for r in cur.fetchall()}
    total = sum(zones.values()) or 1
    indicators["pct_centre"]       = zones.get("centre", 0) / total * 100
    indicators["pct_peripherique"] = zones.get("peripherique", 0) / total * 100
    indicators["pct_intermediaire"]= zones.get("intermediaire", 0) / total * 100

    # 9. Météo
    cur.execute("SELECT temperature_max, precipitation_sum FROM public.dim_meteo ORDER BY date DESC LIMIT 1")
    meteo = cur.fetchone()
    if meteo:
        indicators["temperature"]    = float(meteo["temperature_max"] or 20)
        indicators["precipitation"]  = float(meteo["precipitation_sum"] or 0)
    else:
        indicators["temperature"]   = 20.0
        indicators["precipitation"] = 0.0

    # 10. Population ville
    indicators["population_ville"] = 299096  # Montpellier INSEE 2020
    indicators["superficie_km2"]   = 56.88   # km²

    cur.close()
    return indicators


# =============================================================================
# LILLE INDICATORS
# =============================================================================

def get_lille_indicators(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    indicators = {}

    # 1. Vélo — V'Lille stations
    cur.execute("""
        SELECT COUNT(*) as nb_stations,
               SUM(nb_velos_dispo) as total_velos,
               SUM(nb_places_dispo) as total_places,
               AVG(nb_velos_dispo) as avg_velos
        FROM lille.dim_vlille_stations
        WHERE etat != 'RÉFORMÉ'
    """)
    velo = cur.fetchone()
    indicators["nb_stations_velo"] = float(velo["nb_stations"] or 0)
    indicators["total_capacite"]   = float((velo["total_velos"] or 0) + (velo["total_places"] or 0))
    indicators["avg_capacite"]     = float(velo["avg_velos"] or 0)
    indicators["nb_free_bikes"]    = float(velo["total_velos"] or 0)

    # 2. Transport collectif — arrêts ilévia
    cur.execute("SELECT COUNT(*) as nb FROM lille.dim_arrets")
    tc = cur.fetchone()
    indicators["nb_arrets_tc"] = float(tc["nb"])
    indicators["nb_lignes"]    = 80.0  # ilévia ~80 lignes

    # 3. Parkings
    cur.execute("""
        SELECT COUNT(*) as nb,
               AVG(taux_occupation) as avg_occ
        FROM lille.dim_parkings
    """)
    pk = cur.fetchone()
    indicators["nb_parkings"]         = float(pk["nb"] or 0)
    indicators["taux_occupation_moy"] = float(pk["avg_occ"] or 50)

    # 4. Qualité air
    cur.execute("""
        SELECT AVG(code_qual) as indice, AVG(code_no2) as no2,
               AVG(code_o3) as o3, AVG(code_pm10) as pm10
        FROM lille.dim_qualite_air
        WHERE date_ech = (SELECT MAX(date_ech) FROM lille.dim_qualite_air)
          AND lib_zone ILIKE '%lille%'
        LIMIT 1
    """)
    aqi = cur.fetchone()
    if aqi and aqi["indice"]:
        indicators["indice_qualite"] = float(aqi["indice"] or 3)
        indicators["no2"]  = float(aqi["no2"]  or 2) * 20  # scale to µg/m³ approx
        indicators["o3"]   = float(aqi["o3"]   or 2) * 30
        indicators["pm10"] = float(aqi["pm10"] or 2) * 15
    else:
        indicators["indice_qualite"] = 3.0
        indicators["no2"]  = 20.0
        indicators["o3"]   = 60.0
        indicators["pm10"] = 20.0

    # 5. Démographie
    cur.execute("""
        SELECT AVG(population) as pop, AVG(pct_young_adult) as young,
               AVG(pct_65plus) as senior, AVG(pct_high_income) as rich
        FROM lille.dim_demographics
    """)
    dem = cur.fetchone()
    indicators["population_moy"]  = float(dem["pop"]    or 0)
    indicators["pct_young_adult"] = float(dem["young"]  or 0)
    indicators["pct_65plus"]      = float(dem["senior"] or 0)
    indicators["pct_high_income"] = float(dem["rich"]   or 0)

    # 6. Usage vélo (emprunts)
    cur.execute("SELECT COUNT(*) as nb FROM lille.dim_emprunt_vlille")
    emp = cur.fetchone()
    indicators["nb_emprunts"] = float(emp["nb"] or 0)

    # 7. Bike histo — MJO moyen
    cur.execute("SELECT AVG(mjo) as mjo FROM lille.dim_bike_histo")
    bh = cur.fetchone()
    indicators["mjo_moyen"] = float(bh["mjo"] or 0)

    # 8. Fairness — distribution stations par commune
    cur.execute("""
        SELECT COUNT(DISTINCT commune) as nb_communes,
               COUNT(*) as nb_stations
        FROM lille.dim_vlille_stations
        WHERE etat != 'RÉFORMÉ'
    """)
    fq = cur.fetchone()
    indicators["nb_communes_couvertes"] = float(fq["nb_communes"] or 1)
    indicators["pct_centre"]           = 40.0  # estimé centre Lille
    indicators["pct_peripherique"]     = 30.0

    # 9. Météo
    cur.execute("SELECT temperature_max, precipitation_sum FROM lille.dim_meteo ORDER BY date DESC LIMIT 1")
    meteo = cur.fetchone()
    if meteo:
        indicators["temperature"]   = float(meteo["temperature_max"] or 15)
        indicators["precipitation"] = float(meteo["precipitation_sum"] or 0)
    else:
        indicators["temperature"]   = 15.0
        indicators["precipitation"] = 2.0

    # 10. Population ville
    indicators["population_ville"] = 233098  # Lille INSEE 2020
    indicators["superficie_km2"]   = 34.84   # km²

    cur.close()
    return indicators


# =============================================================================
# CALCUL IMD — ITDP ADAPTÉ
# =============================================================================

def compute_imd(indicators, ville):
    """
    Calcule l'Indice de Mobilité Durable (IMD) sur 100.
    8 dimensions ITDP adaptées à nos données disponibles.
    """
    scores = {}

    pop    = indicators["population_ville"]
    area   = indicators["superficie_km2"]
    densite = pop / area if area > 0 else 0

    # ── D1. MARCHE (10%) ──────────────────────────────────────────────────────
    # Proxy: densité arrêts TC / km² (plus d'arrêts = plus marchable)
    arrets_per_km2 = indicators["nb_arrets_tc"] / area
    scores["marche"] = min(100, arrets_per_km2 * 5)

    # ── D2. VÉLO (20%) ────────────────────────────────────────────────────────
    stations_per_km2 = indicators["nb_stations_velo"] / area
    velos_per_hab    = indicators["nb_free_bikes"] / pop * 1000  # pour 1000 hab
    scores["velo"]   = min(100, (stations_per_km2 * 20 + velos_per_hab * 10))

    # ── D3. TRANSPORT COLLECTIF (20%) ─────────────────────────────────────────
    arrets_score  = min(100, arrets_per_km2 * 3)
    lignes_score  = min(100, indicators["nb_lignes"] * 1.5)
    scores["transport"] = (arrets_score * 0.6 + lignes_score * 0.4)

    # ── D4. MIX USAGE / MULTIMODALITÉ (10%) ──────────────────────────────────
    # Proxy: nombre de modes disponibles × coverage
    modes = 0
    if indicators["nb_stations_velo"] > 0: modes += 1
    if indicators["nb_arrets_tc"]     > 0: modes += 1
    if indicators["nb_parkings"]      > 0: modes += 1
    if indicators.get("nb_free_bikes", 0) > 0: modes += 1
    scores["mix_usage"] = modes / 4 * 100

    # ── D5. DENSITÉ (10%) ─────────────────────────────────────────────────────
    # Densité population (hab/km²) — normalisée entre 1000 et 15000
    scores["densite"] = normalize(densite, 1000, 15000)

    # ── D6. COMPACITÉ (10%) ───────────────────────────────────────────────────
    # Concentration services mobilité
    total_services = (indicators["nb_stations_velo"] +
                      indicators["nb_arrets_tc"] / 10 +
                      indicators["nb_parkings"])
    services_per_km2  = total_services / area
    scores["compacite"] = min(100, services_per_km2 * 2)

    # ── D7. CONNECTIVITÉ / ÉQUITÉ (10%) ──────────────────────────────────────
    # Distribution spatiale équitable
    equite = 100 - abs(indicators["pct_centre"] - indicators["pct_peripherique"])
    scores["connectivite"] = max(0, equite)

    # ── D8. ENVIRONNEMENT (10%) ───────────────────────────────────────────────
    # AQI inversé (meilleur = plus bas indice) + précipitations
    aqi_score   = normalize(indicators["indice_qualite"], 1, 6, inverse=True)
    pm10_score  = normalize(indicators["pm10"], 0, 50, inverse=True)
    scores["environnement"] = aqi_score * 0.6 + pm10_score * 0.4

    # ── IMD COMPOSITE (pondération ITDP adaptée) ─────────────────────────────
    weights = {
        "marche":       0.10,
        "velo":         0.20,
        "transport":    0.20,
        "mix_usage":    0.10,
        "densite":      0.10,
        "compacite":    0.10,
        "connectivite": 0.10,
        "environnement":0.10,
    }

    imd = sum(scores[dim] * weights[dim] for dim in weights)

    return {
        "ville":         ville,
        "imd_score":     round(imd, 2),
        "scores":        {k: round(v, 2) for k, v in scores.items()},
        "indicators":    {k: round(float(v), 2) for k, v in indicators.items()},
        "computed_at":   datetime.now().isoformat(),
        "methodology":   "ITDP Urban Mobility Index — adapté méthode suédoise",
        "scale":         "0 à 100 (100 = mobilité parfaitement durable)"
    }


# =============================================================================
# SAVE TO DB
# =============================================================================

def save_results(results):
    conn = get_pg()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.dim_imd_scores (
            ville        VARCHAR PRIMARY KEY,
            imd_score    FLOAT,
            score_marche      FLOAT,
            score_velo        FLOAT,
            score_transport   FLOAT,
            score_mix_usage   FLOAT,
            score_densite     FLOAT,
            score_compacite   FLOAT,
            score_connectivite FLOAT,
            score_environnement FLOAT,
            details      JSONB,
            computed_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    for r in results:
        s = r["scores"]
        cur.execute("""
            INSERT INTO public.dim_imd_scores
            (ville, imd_score, score_marche, score_velo, score_transport,
             score_mix_usage, score_densite, score_compacite,
             score_connectivite, score_environnement, details)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (ville) DO UPDATE SET
                imd_score = EXCLUDED.imd_score,
                score_velo = EXCLUDED.score_velo,
                details = EXCLUDED.details,
                computed_at = NOW()
        """, (
            r["ville"], r["imd_score"],
            s["marche"], s["velo"], s["transport"], s["mix_usage"],
            s["densite"], s["compacite"], s["connectivite"], s["environnement"],
            json.dumps(r)
        ))

    conn.commit()
    cur.close()
    conn.close()
    print("  Results saved → public.dim_imd_scores")


# =============================================================================
# MAIN
# =============================================================================

def compute_imd_normalized(mtp_ind, lil_ind):
    """
    Calcule IMD avec des valeurs de référence absolues
    basées sur les standards européens de mobilité durable.
    """
    results = []

    # Références européennes (villes durables de référence)
    REF = {
        "arrets_km2_min":    5,    "arrets_km2_max":    80,
        "stations_km2_min":  0.5,  "stations_km2_max":  8,
        "velos_hab_min":     0.5,  "velos_hab_max":     10,
        "lignes_min":        10,   "lignes_max":        100,
        "densite_min":       1000, "densite_max":       15000,
        "svc_km2_min":       1,    "svc_km2_max":       50,
        "aqi_min":           1,    "aqi_max":           6,
        "pm10_min":          5,    "pm10_max":          50,
    }

    for ville, ind in [("Montpellier", mtp_ind), ("Lille", lil_ind)]:
        pop   = ind["population_ville"]
        area  = ind["superficie_km2"]
        densite = pop / area

        scores = {}

        # D1. MARCHE — arrêts TC / km²
        arrets_km2 = ind["nb_arrets_tc"] / area
        scores["marche"] = normalize(arrets_km2, REF["arrets_km2_min"], REF["arrets_km2_max"])

        # D2. VÉLO — stations/km² + vélos/1000 hab
        s_km2   = ind["nb_stations_velo"] / area
        v_hab   = ind["nb_free_bikes"] / pop * 1000
        s_score = normalize(s_km2, REF["stations_km2_min"], REF["stations_km2_max"])
        v_score = normalize(v_hab, REF["velos_hab_min"],    REF["velos_hab_max"])
        scores["velo"] = s_score * 0.6 + v_score * 0.4

        # D3. TRANSPORT — arrêts + lignes
        a_score = normalize(ind["nb_arrets_tc"] / area, REF["arrets_km2_min"], REF["arrets_km2_max"])
        l_score = normalize(ind["nb_lignes"],            REF["lignes_min"],     REF["lignes_max"])
        scores["transport"] = a_score * 0.6 + l_score * 0.4

        # D4. MIX USAGE
        modes = sum([
            ind["nb_stations_velo"] > 0,
            ind["nb_arrets_tc"]     > 0,
            ind["nb_parkings"]      > 0,
            ind.get("nb_free_bikes", 0) > 0
        ])
        scores["mix_usage"] = modes / 4 * 100

        # D5. DENSITÉ
        scores["densite"] = normalize(densite, REF["densite_min"], REF["densite_max"])

        # D6. COMPACITÉ
        svc_km2 = (ind["nb_stations_velo"] + ind["nb_arrets_tc"] / 10 + ind["nb_parkings"]) / area
        scores["compacite"] = normalize(svc_km2, REF["svc_km2_min"], REF["svc_km2_max"])

        # D7. CONNECTIVITÉ / ÉQUITÉ — distribution équilibrée entre zones
        pct_c = ind["pct_centre"]
        pct_i = ind.get("pct_intermediaire", 0)
        pct_p = ind["pct_peripherique"]
        # Score idéal: 33% chaque zone
        ideal = 33.33
        ecart = (abs(pct_c - ideal) + abs(pct_i - ideal) + abs(pct_p - ideal)) / 3
        scores["connectivite"] = max(0, 100 - ecart * 2)

        # D8. ENVIRONNEMENT
        aqi_score = normalize(ind["indice_qualite"], REF["aqi_min"],  REF["aqi_max"],  inverse=True)
        pm_score  = normalize(ind["pm10"],           REF["pm10_min"], REF["pm10_max"], inverse=True)
        scores["environnement"] = aqi_score * 0.6 + pm_score * 0.4

        weights = {
            "marche": 0.10, "velo": 0.15, "transport": 0.15,
            "mix_usage": 0.15, "densite": 0.05, "compacite": 0.05,
            "connectivite": 0.20, "environnement": 0.15
        }
        imd = sum(scores[d] * weights[d] for d in weights)

        results.append({
            "ville":      ville,
            "imd_score":  round(imd, 2),
            "scores":     {k: round(v, 2) for k, v in scores.items()},
            "indicators": {k: round(float(v), 2) for k, v in ind.items()},
            "computed_at": datetime.now().isoformat(),
            "methodology": "ITDP Urban Mobility Index — adapté méthode suédoise — références européennes",
            "scale": "0 à 100 (100 = standard européen de référence)"
        })

    return results


if __name__ == "__main__":
    print("MODALITY-FLOW — Calcul IMD")
    print("Méthodologie: ITDP + Méthode suédoise")
    print("=" * 50)

    conn = get_pg()

    print("\n📍 Montpellier...")
    mtp_ind = get_montpellier_indicators(conn)

    print("\n📍 Lille...")
    lil_ind = get_lille_indicators(conn)

    conn.close()

    results = compute_imd_normalized(mtp_ind, lil_ind)
    save_results(results)

    print("\n" + "=" * 50)
    print("RÉSULTATS — Indice de Mobilité Durable")
    print("=" * 50)
    for r in results:
        print(f"\n🏙️  {r['ville']}")
        print(f"   IMD Score: {r['imd_score']}/100")
        print(f"   Détail:")
        for dim, score in r["scores"].items():
            bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
            print(f"     {dim:<15} {bar} {score:.1f}")

    diff = results[0]["imd_score"] - results[1]["imd_score"]
    winner = results[0]["ville"] if diff > 0 else results[1]["ville"]
    print(f"\n🏆 {winner} obtient le meilleur score IMD")
    print(f"   Écart: {abs(diff):.1f} points")
    print(f"\nRésultats sauvegardés → public.dim_imd_scores")
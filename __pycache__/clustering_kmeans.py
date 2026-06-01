"""
clustering_kmeans.py
====================
K-Means clustering des stations Velomagg de Montpellier.
Résultats sauvegardés dans PostgreSQL Railway : table dim_station_clusters

Usage :
    python clustering_kmeans.py

Dépendances :
    pip install scikit-learn pandas psycopg2-binary numpy
"""

import os
import json
import psycopg2
import psycopg2.extras
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# ── Configuration ────────────────────────────────────────────────────────────
DATABASE_URL = "postgresql://postgres:PfbeGtHyxglIyRBZppgxBxPtYMQUmoyy@gondola.proxy.rlwy.net:46226/railway"

# ── Connexion PostgreSQL ──────────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# ── Chargement des données ────────────────────────────────────────────────────
def load_stations():
    conn = get_conn()
    query = """
        SELECT
            s.station_id,
            s.nom,
            s.lat,
            s.lon,
            s.capacite,
            SQRT(
                POWER((s.lat - 43.6109) * 111, 2) +
                POWER((s.lon - 3.8763) * 85, 2)
            ) AS dist_centre_km,
            COALESCE(d.pct_low_income, 22.0)    AS pct_low_income,
            COALESCE(d.pct_high_income, 18.0)   AS pct_high_income,
            COALESCE(d.pct_young_adult, 28.0)   AS pct_young_adult,
            COALESCE(d.pct_65plus, 14.0)        AS pct_65plus
        FROM public.dim_stations s
        LEFT JOIN public.dim_communes_demographics d
            ON s.codgeo = d.codgeo
        WHERE s.capacite > 0
          AND s.lat BETWEEN 43.55 AND 43.70
          AND s.lon BETWEEN 3.75 AND 4.00
        ORDER BY s.station_id
    """
    df = pd.read_sql(query, conn)
    conn.close()
    print(f"Stations chargées : {len(df)}")
    return df

# ── Disponibilité moyenne par station ────────────────────────────────────────
def load_availability(df):
    conn = get_conn()
    query = """
        SELECT
            station_id,
            AVG(bisiklet_sayisi)                          AS avg_bikes,
            STDDEV(bisiklet_sayisi)                       AS std_bikes,
            COUNT(*)                                      AS nb_mesures,
            AVG(CASE WHEN bisiklet_sayisi = 0 THEN 1 ELSE 0 END) AS taux_vide
        FROM public.fact_velomagg_historique
        GROUP BY station_id
    """
    avail = pd.read_sql(query, conn)
    conn.close()
    df = df.merge(avail, on="station_id", how="left")
    df["avg_bikes"]  = df["avg_bikes"].fillna(df["capacite"] * 0.4)
    df["std_bikes"]  = df["std_bikes"].fillna(2.0)
    df["taux_vide"]  = df["taux_vide"].fillna(0.1)
    df["nb_mesures"] = df["nb_mesures"].fillna(0)
    return df

# ── Choix du nombre optimal de clusters ──────────────────────────────────────
def optimal_k(X_scaled, k_range=range(2, 7)):
    inertias, silhouettes = [], []
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(X_scaled)
        inertias.append(km.inertia_)
        silhouettes.append(silhouette_score(X_scaled, km.labels_))
    best_k = list(k_range)[silhouettes.index(max(silhouettes))]
    print(f"\nSilhouette scores : {dict(zip(k_range, [round(s,3) for s in silhouettes]))}")
    print(f"K optimal (silhouette) : {best_k}")
    return best_k, silhouettes

# ── Features de clustering ────────────────────────────────────────────────────
FEATURES = [
    "dist_centre_km",   # distance au centre-ville
    "capacite",         # taille de la station
    "avg_bikes",        # disponibilité moyenne
    "taux_vide",        # fréquence stations vides
    "pct_low_income",   # contexte socio-éco
    "pct_young_adult",  # démographie
]

# ── Labels des clusters ───────────────────────────────────────────────────────
CLUSTER_LABELS = {
    0: "Centre — forte utilisation",
    1: "Intermédiaire — usage modéré",
    2: "Périphérique — sous-utilisé",
    3: "Prioritaire — faible accès",
}

CLUSTER_PRIORITY = {
    0: "low",
    1: "medium",
    2: "high",
    3: "critical",
}

CLUSTER_COLORS = {
    0: "#1D9E75",   # vert
    1: "#378ADD",   # bleu
    2: "#BA7517",   # orange
    3: "#E24B4A",   # rouge
}

# ── Création table PostgreSQL ─────────────────────────────────────────────────
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS public.dim_station_clusters (
    station_id      VARCHAR PRIMARY KEY,
    nom             VARCHAR,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    cluster_id      INTEGER,
    cluster_label   VARCHAR,
    cluster_priority VARCHAR,
    cluster_color   VARCHAR,
    dist_centre_km  DOUBLE PRECISION,
    capacite        INTEGER,
    avg_bikes       DOUBLE PRECISION,
    taux_vide       DOUBLE PRECISION,
    silhouette_score DOUBLE PRECISION,
    features        JSONB,
    computed_at     TIMESTAMP DEFAULT NOW()
);
"""

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  MODALITY-FLOW — Clustering K-Means stations Velomagg")
    print("=" * 55)

    # 1. Chargement
    df = load_stations()
    df = load_availability(df)

    # 2. Features
    X = df[FEATURES].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 3. Choix k optimal
    best_k, silhouettes = optimal_k(X_scaled)

    # 4. K-Means final
    km = KMeans(n_clusters=best_k, random_state=42, n_init=20)
    df["cluster_id"] = km.fit_predict(X_scaled)

    # Score silhouette global
    global_silhouette = round(silhouette_score(X_scaled, df["cluster_id"]), 4)
    print(f"Silhouette score global : {global_silhouette}")

    # 5. Réassignation clusters par dist_centre (pour cohérence labels)
    # Cluster le plus proche du centre = cluster 0
    cluster_dist = df.groupby("cluster_id")["dist_centre_km"].mean().sort_values()
    mapping = {old: new for new, old in enumerate(cluster_dist.index)}
    df["cluster_id"] = df["cluster_id"].map(mapping)

    # 6. Résultats
    df["cluster_label"]    = df["cluster_id"].map(
        lambda x: CLUSTER_LABELS.get(x, f"Cluster {x}"))
    df["cluster_priority"] = df["cluster_id"].map(
        lambda x: CLUSTER_PRIORITY.get(x, "medium"))
    df["cluster_color"]    = df["cluster_id"].map(
        lambda x: CLUSTER_COLORS.get(x, "#666666"))

    # Affichage résumé
    print("\nRésumé des clusters :")
    summary = df.groupby(["cluster_id", "cluster_label"]).agg(
        nb_stations=("station_id", "count"),
        dist_moy=("dist_centre_km", "mean"),
        capacite_moy=("capacite", "mean"),
        avg_bikes_moy=("avg_bikes", "mean"),
        taux_vide_moy=("taux_vide", "mean"),
    ).round(2)
    print(summary.to_string())

    # 7. Zones prioritaires
    print("\nZones prioritaires (cluster priority=high ou critical) :")
    prioritaires = df[df["cluster_priority"].isin(["high", "critical"])][
        ["nom", "cluster_label", "dist_centre_km", "avg_bikes", "taux_vide"]
    ].sort_values("dist_centre_km")
    print(prioritaires.to_string(index=False))

    # 8. Sauvegarde PostgreSQL
    print("\nSauvegarde dans PostgreSQL Railway...")
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(CREATE_TABLE)
    cur.execute("DELETE FROM public.dim_station_clusters")

    for _, row in df.iterrows():
        features_json = json.dumps({f: round(float(row[f]), 4) for f in FEATURES})
        cur.execute("""
            INSERT INTO public.dim_station_clusters
                (station_id, nom, lat, lon, cluster_id, cluster_label,
                 cluster_priority, cluster_color, dist_centre_km, capacite,
                 avg_bikes, taux_vide, silhouette_score, features)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            row["station_id"], row["nom"], row["lat"], row["lon"],
            int(row["cluster_id"]), row["cluster_label"],
            row["cluster_priority"], row["cluster_color"],
            round(float(row["dist_centre_km"]), 3),
            int(row["capacite"]),
            round(float(row["avg_bikes"]), 2),
            round(float(row["taux_vide"]), 4),
            global_silhouette,
            features_json
        ))

    conn.commit()
    cur.close()
    conn.close()

    print(f"OK — {len(df)} stations insérées dans dim_station_clusters")
    print(f"Silhouette score : {global_silhouette}")
    print("\nEndpoint API disponible : GET /fairness")
    print("Nouvelle table : public.dim_station_clusters")

if __name__ == "__main__":
    main()

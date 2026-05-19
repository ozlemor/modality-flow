"""
MODALITY-FLOW — Demographic ETL
Loads INSEE commune-level population data into Railway PostgreSQL.

Requirements:
    pip install psycopg2-binary pandas numpy
"""

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
import warnings
warnings.filterwarnings('ignore')

# --- CONFIG -------------------------------------------------------------------
DB_URL   = "postgresql://postgres:PfbeGtHyxglIyRBZppgxBxPtYMQUmoyy@gondola.proxy.rlwy.net:46226/railway"
CSV_PATH = "/Users/ozlemdechamps/Desktop/Velo/base-cc-evol-struct-pop-2020_csv/base-cc-evol-struct-pop-2020.CSV"

# INSEE commune codes for Montpellier Mediterranee Metropole (31 communes)
METROPOLE_CODES = [
    '34013','34022','34027','34057','34058','34065','34068','34088','34090',
    '34116','34120','34129','34134','34154','34157','34169','34172','34179',
    '34198','34202','34214','34217','34228','34244','34270','34283','34295',
    '34297','34337','34338','34340'
]


# --- 1. LOAD AND PROCESS CSV --------------------------------------------------
def process_csv(csv_path):
    print("Loading INSEE CSV...")
    df = pd.read_csv(csv_path, sep=';', dtype={'CODGEO': str})
    df_metro = df[df['CODGEO'].isin(METROPOLE_CODES)].copy()
    print(f"  {len(df_metro)} communes found")

    pop   = df_metro['P20_POP'].replace(0, np.nan)
    pop15 = df_metro['C20_POP15P'].replace(0, np.nan)

    out = pd.DataFrame()
    out['codgeo']     = df_metro['CODGEO'].values
    out['population'] = df_metro['P20_POP'].values

    # Age group shares (% of total population)
    out['pct_youth']       = (df_metro['P20_POP0014'] / pop * 100).round(2).values                                   # 0-14
    out['pct_young_adult'] = (df_metro['P20_POP1529'] / pop * 100).round(2).values                                   # 15-29
    out['pct_active']      = ((df_metro['P20_POP3044'] + df_metro['P20_POP4559']) / pop * 100).round(2).values       # 30-59
    out['pct_senior']      = (df_metro['P20_POP6074'] / pop * 100).round(2).values                                   # 60-74
    out['pct_elderly']     = ((df_metro['P20_POP7589'] + df_metro['P20_POP90P']) / pop * 100).round(2).values        # 75+

    # Socio-professional categories CS1-CS8 (% of population aged 15+)
    cs_map = {
        'CS1': 'pct_agriculteurs',
        'CS2': 'pct_artisans_commercants',
        'CS3': 'pct_cadres',
        'CS4': 'pct_professions_intermediaires',
        'CS5': 'pct_employes',
        'CS6': 'pct_ouvriers',
        'CS7': 'pct_retraites',
        'CS8': 'pct_autres_inactifs',
    }
    for cs, col_name in cs_map.items():
        out[col_name] = (df_metro[f'C20_POP15P_{cs}'] / pop15 * 100).round(2).values

    # Derived features used by the ML model and fairness analysis
    out['pct_high_income'] = out['pct_cadres']                           # cadres as high-income proxy
    out['pct_low_income']  = out['pct_employes'] + out['pct_ouvriers']   # low-income proxy
    out['pct_65plus']      = out['pct_senior'] + out['pct_elderly']      # accessibility indicator

    print(f"  {len(out.columns)} columns computed")
    print(out[['codgeo', 'population', 'pct_high_income', 'pct_low_income', 'pct_65plus', 'pct_young_adult']].to_string())
    return out


# --- 2. UPLOAD TO POSTGRESQL --------------------------------------------------
def upload_to_postgres(df):
    print("\nConnecting to Railway PostgreSQL...")
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    cur.execute("""
        DROP TABLE IF EXISTS public.dim_communes_demographics CASCADE;
        CREATE TABLE public.dim_communes_demographics (
            codgeo                         VARCHAR(10) PRIMARY KEY,
            population                     FLOAT,
            pct_youth                      FLOAT,
            pct_young_adult                FLOAT,
            pct_active                     FLOAT,
            pct_senior                     FLOAT,
            pct_elderly                    FLOAT,
            pct_agriculteurs               FLOAT,
            pct_artisans_commercants       FLOAT,
            pct_cadres                     FLOAT,
            pct_professions_intermediaires FLOAT,
            pct_employes                   FLOAT,
            pct_ouvriers                   FLOAT,
            pct_retraites                  FLOAT,
            pct_autres_inactifs            FLOAT,
            pct_high_income                FLOAT,
            pct_low_income                 FLOAT,
            pct_65plus                     FLOAT,
            updated_at                     TIMESTAMP DEFAULT NOW()
        );
    """)

    # Convert NaN to None for PostgreSQL NULL compatibility
    values = [
        tuple(None if (isinstance(v, float) and np.isnan(v)) else v for v in row)
        for row in df.values
    ]
    cols = ', '.join(df.columns)
    execute_values(
        cur,
        f"INSERT INTO public.dim_communes_demographics ({cols}) VALUES %s",
        values
    )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM public.dim_communes_demographics")
    count = cur.fetchone()[0]
    print(f"  {count} rows inserted into public.dim_communes_demographics")

    cur.close()
    conn.close()


# --- 3. ADD CODGEO COLUMN TO DIM_STATIONS -------------------------------------
def add_codgeo_to_stations():
    """
    All Velomagg stations are located in Montpellier (34172).
    A codgeo column is added to dim_stations to enable demographic joins.
    """
    print("\nAdding codgeo column to dim_stations...")
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    cur.execute("""
        ALTER TABLE public.dim_stations
            ADD COLUMN IF NOT EXISTS codgeo VARCHAR(10) DEFAULT '34172';
        UPDATE public.dim_stations
            SET codgeo = '34172'
            WHERE codgeo IS NULL OR codgeo = '';
    """)
    conn.commit()
    print("  All Velomagg stations assigned codgeo = '34172' (Montpellier)")

    cur.close()
    conn.close()


# --- 4. CREATE VIEWS ----------------------------------------------------------
def create_views():
    print("\nCreating views...")
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    # Joins station metadata with commune-level demographics for ML feature extraction
    cur.execute("""
        CREATE OR REPLACE VIEW public.v_ml_features_with_demographics AS
        SELECT
            s.station_id,
            s.nom,
            s.lat,
            s.lon,
            s.capacite,
            s.codgeo,
            d.population,
            d.pct_youth,
            d.pct_young_adult,
            d.pct_active,
            d.pct_senior,
            d.pct_elderly,
            d.pct_65plus,
            d.pct_high_income,
            d.pct_low_income,
            d.pct_cadres,
            d.pct_employes,
            d.pct_ouvriers,
            d.pct_retraites
        FROM public.dim_stations s
        LEFT JOIN public.dim_communes_demographics d ON s.codgeo = d.codgeo;
    """)
    print("  View created: public.v_ml_features_with_demographics")

    # Classifies each station by distance from city centre for fairness analysis
    cur.execute("""
        CREATE OR REPLACE VIEW public.v_station_fairness AS
        SELECT
            s.station_id,
            s.nom,
            s.lat,
            s.lon,
            d.pct_high_income,
            d.pct_low_income,
            d.pct_65plus,
            d.pct_young_adult,
            CASE
                WHEN SQRT(POWER((s.lat - 43.6109) * 111, 2) + POWER((s.lon - 3.8763) * 85, 2)) < 1.5
                     THEN 'centre'
                WHEN SQRT(POWER((s.lat - 43.6109) * 111, 2) + POWER((s.lon - 3.8763) * 85, 2)) < 3.0
                     THEN 'intermediaire'
                ELSE 'peripherique'
            END AS zone,
            ROUND(
                SQRT(POWER((s.lat - 43.6109) * 111, 2) + POWER((s.lon - 3.8763) * 85, 2))::numeric,
            2) AS dist_centre_km
        FROM public.dim_stations s
        LEFT JOIN public.dim_communes_demographics d ON s.codgeo = d.codgeo;
    """)
    print("  View created: public.v_station_fairness")

    conn.commit()
    cur.close()
    conn.close()


# --- MAIN ---------------------------------------------------------------------
if __name__ == "__main__":
    # Set to True to re-run all steps, False to only recreate views
    FULL_RUN = False

    if FULL_RUN:
        df = process_csv(CSV_PATH)
        upload_to_postgres(df)
        add_codgeo_to_stations()

    create_views()

    print("\nETL complete.")
    print("Tables and views available in Railway PostgreSQL:")
    print("  public.dim_communes_demographics")
    print("  public.v_ml_features_with_demographics")
    print("  public.v_station_fairness")
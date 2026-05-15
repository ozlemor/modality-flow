import os, sys, requests, urllib.parse, logging
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_PUBLIC_URL", "")
_url = urllib.parse.urlparse(DATABASE_URL)
PG_CONFIG = {
    "host": _url.hostname, "port": _url.port or 5432,
    "database": _url.path[1:], "user": _url.username,
    "password": _url.password,
    "sslmode": "require" if "railway" in DATABASE_URL else "prefer"
}

GBFS_BASE = "https://gbfs.theta.fifteen.eu/gbfs/2.2/montpellier/en"
API_PARKINGS = "https://portail-api-data.montpellier3m.fr/offstreetparking?limit=1000"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def fetch(url):
    r = requests.get(url, headers={"accept": "application/json"}, timeout=15)
    r.raise_for_status()
    return r.json()

def run():
    import psycopg2
    con = psycopg2.connect(**PG_CONFIG)
    cur = con.cursor()
    NOW = now_iso()

    # 1. fact_station_status
    data = fetch(f"{GBFS_BASE}/station_status.json")
    stations = data.get("data", {}).get("stations", [])
    for s in stations:
        cur.execute("""
            INSERT INTO modality.fact_station_status
            (station_id, bikes_available, docks_available, is_renting, is_returning, timestamp, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, [s["station_id"], s.get("num_bikes_available", 0),
              s.get("num_docks_available", 0),
              s.get("is_renting", False), s.get("is_returning", False),
              NOW, "gbfs"])
    log.info(f"fact_station_status: {len(stations)} statuts")

    # 2. fact_parkings_status
    data = fetch(API_PARKINGS)
    count = 0
    for p in data:
        loc = p.get("location", {}).get("value", {}).get("coordinates", [0,0])
        total = p.get("totalSpotNumber", {}).get("value", 0) or 0
        free = p.get("availableSpotNumber", {}).get("value", 0) or 0
        cur.execute("""
            INSERT INTO modality.fact_parkings_status
            (parking_id, free_spots, total_spots, taux_occupation, status, lat, lon, timestamp)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, [p.get("id"), int(free), int(total),
              round((total-free)/max(total,1)*100,1),
              str(p.get("status",{}).get("value","unknown")),
              float(loc[1]) if len(loc)>1 else 0,
              float(loc[0]) if len(loc)>0 else 0, NOW])
        count += 1
    log.info(f"fact_parkings_status: {count} parkings")

    # 3. fact_free_bikes
    data = fetch(f"{GBFS_BASE}/free_bike_status.json")
    bikes = data.get("data", {}).get("bikes", [])
    for b in bikes:
        cur.execute("""
            INSERT INTO modality.fact_free_bikes
            (bike_id, lat, lon, is_reserved, is_disabled, vehicle_type_id, timestamp)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (bike_id) DO UPDATE
            SET lat=EXCLUDED.lat, lon=EXCLUDED.lon, timestamp=EXCLUDED.timestamp
        """, [b.get("bike_id"), b.get("lat",0), b.get("lon",0),
              b.get("is_reserved",False), b.get("is_disabled",False),
              b.get("vehicle_type_id",""), NOW])
    log.info(f"fact_free_bikes: {len(bikes)} vélos")

    con.commit()
    cur.close()
    con.close()
    log.info("Real-time update terminé")

if __name__ == "__main__":
    run()
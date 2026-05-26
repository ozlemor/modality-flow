"""
MODALITY-FLOW — Kafka Producer
Fetches real-time data from APIs and sends to Kafka topics.

Topics:
  - velomagg.station_status   (every 1 min)
  - velomagg.free_bikes       (every 1 min)
  - parking.status            (every 5 min)
  - tam.trip_updates          (every 30 sec)
  - tam.vehicle_positions     (every 30 sec)
  - environnement.meteo       (every 1 hour)
  - environnement.aqi         (every 1 hour)

Usage:
    cd ~/Desktop/Velo
    python3 kafka_producer.py
"""

import json
import time
import logging
import requests
from datetime import datetime, timezone
from kafka import KafkaProducer
from kafka.errors import KafkaError

# --- CONFIG -------------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVER = "localhost:9092"

GBFS_BASE    = "https://gbfs.theta.fifteen.eu/gbfs/2.2/montpellier/en"
API_PARKINGS = "https://portail-api-data.montpellier3m.fr/offstreetparking?limit=1000"
API_METEO    = "https://api.open-meteo.com/v1/forecast?latitude=43.6109&longitude=3.8763&current=temperature_2m,precipitation,wind_speed_10m,weather_code&timezone=Europe/Paris"
API_AQI      = "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=43.6109&longitude=3.8763&current=pm10,pm2_5,nitrogen_dioxide,ozone&timezone=Europe/Paris"
API_TAM_TRIP = "https://data.montpellier3m.fr/GTFS/Urbain/TripUpdate.pb"
API_TAM_VEH  = "https://data.montpellier3m.fr/GTFS/Urbain/VehiclePosition.pb"

# Update intervals in seconds
INTERVALS = {
    "velomagg":  60,
    "parking":   300,
    "tam":       30,
    "meteo":     3600,
    "aqi":       3600,
}

# --- LOGGING ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("kafka_producer")


# --- KAFKA PRODUCER -----------------------------------------------------------
def create_producer():
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVER,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False, default=str).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
        retries=3,
    )


def send(producer, topic, key, value):
    try:
        future = producer.send(topic, key=key, value=value)
        producer.flush()
        log.info(f"  Sent → {topic} | key={key}")
        return True
    except KafkaError as e:
        log.error(f"  Kafka error on {topic}: {e}")
        return False


# --- FETCH HELPERS ------------------------------------------------------------
def fetch_json(url, timeout=15):
    try:
        r = requests.get(url, headers={"accept": "application/json"}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"  Fetch failed {url}: {e}")
        return None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# --- PRODUCERS ----------------------------------------------------------------
def produce_velomagg(producer):
    log.info("Fetching Velomagg station status...")
    data = fetch_json(f"{GBFS_BASE}/station_status.json")
    if not data:
        return

    stations = data.get("data", {}).get("stations", [])
    for s in stations:
        msg = {
            "station_id":      s.get("station_id"),
            "bikes_available": s.get("num_bikes_available", 0),
            "docks_available": s.get("num_docks_available", 0),
            "is_renting":      s.get("is_renting", False),
            "is_returning":    s.get("is_returning", False),
            "timestamp":       now_iso(),
            "source":          "gbfs"
        }
        send(producer, "velomagg.station_status", msg["station_id"], msg)

    log.info(f"  {len(stations)} stations sent → velomagg.station_status")


def produce_free_bikes(producer):
    log.info("Fetching free bikes...")
    data = fetch_json(f"{GBFS_BASE}/free_bike_status.json")
    if not data:
        return

    bikes = data.get("data", {}).get("bikes", [])
    for b in bikes:
        msg = {
            "bike_id":         b.get("bike_id"),
            "lat":             b.get("lat", 0),
            "lon":             b.get("lon", 0),
            "is_reserved":     b.get("is_reserved", False),
            "is_disabled":     b.get("is_disabled", False),
            "vehicle_type_id": b.get("vehicle_type_id", ""),
            "timestamp":       now_iso(),
        }
        send(producer, "velomagg.free_bikes", msg["bike_id"], msg)

    log.info(f"  {len(bikes)} bikes sent → velomagg.free_bikes")


def produce_parkings(producer):
    log.info("Fetching parking status...")
    data = fetch_json(API_PARKINGS)
    if not data:
        return

    count = 0
    for p in data:
        loc   = p.get("location", {}).get("value", {}).get("coordinates", [0, 0])
        total = p.get("totalSpotNumber", {}).get("value", 0) or 0
        free  = p.get("availableSpotNumber", {}).get("value", 0) or 0
        pid   = p.get("id", "")

        msg = {
            "parking_id":      pid,
            "free_spots":      int(free),
            "total_spots":     int(total),
            "taux_occupation": round((total - free) / max(total, 1) * 100, 1),
            "status":          str(p.get("status", {}).get("value", "unknown")),
            "lat":             float(loc[1]) if len(loc) > 1 else 0,
            "lon":             float(loc[0]) if len(loc) > 0 else 0,
            "timestamp":       now_iso(),
        }
        send(producer, "parking.status", pid, msg)
        count += 1

    log.info(f"  {count} parkings sent → parking.status")


def produce_meteo(producer):
    log.info("Fetching weather...")
    data = fetch_json(API_METEO)
    if not data:
        return

    current = data.get("current", {})
    msg = {
        "temperature":    current.get("temperature_2m"),
        "precipitation":  current.get("precipitation"),
        "wind_speed":     current.get("wind_speed_10m"),
        "weather_code":   current.get("weather_code"),
        "timestamp":      now_iso(),
        "source":         "open-meteo"
    }
    send(producer, "environnement.meteo", "montpellier", msg)
    log.info("  Weather sent → environnement.meteo")


def produce_aqi(producer):
    log.info("Fetching air quality...")
    data = fetch_json(API_AQI)
    if not data:
        return

    current = data.get("current", {})
    msg = {
        "pm10":  current.get("pm10"),
        "pm25":  current.get("pm2_5"),
        "no2":   current.get("nitrogen_dioxide"),
        "o3":    current.get("ozone"),
        "timestamp": now_iso(),
        "source":    "open-meteo-air-quality"
    }
    send(producer, "environnement.aqi", "montpellier", msg)
    log.info("  AQI sent → environnement.aqi")


def produce_tam(producer):
    """
    TAM GTFS-RT uses protobuf format.
    For now we send a status ping — full protobuf parsing in next sprint.
    """
    log.info("Fetching TAM GTFS-RT...")
    try:
        r = requests.get(API_TAM_TRIP, timeout=15)
        msg = {
            "status":    "received",
            "size_bytes": len(r.content),
            "timestamp": now_iso(),
            "note":      "protobuf — full parsing in next sprint"
        }
        send(producer, "tam.trip_updates", "tam", msg)
        log.info("  TAM trip updates ping sent → tam.trip_updates")
    except Exception as e:
        log.warning(f"  TAM fetch failed: {e}")


# --- MAIN LOOP ----------------------------------------------------------------
def run():
    log.info("MODALITY-FLOW Kafka Producer starting...")
    log.info(f"  Kafka: {KAFKA_BOOTSTRAP_SERVER}")

    producer = create_producer()
    log.info("  Connected to Kafka")

    # Track last run times
    last = {k: 0 for k in INTERVALS}

    log.info("  Producer running — press Ctrl+C to stop")

    while True:
        now = time.time()

        # Velomagg — every 1 min
        if now - last["velomagg"] >= INTERVALS["velomagg"]:
            produce_velomagg(producer)
            produce_free_bikes(producer)
            last["velomagg"] = now

        # Parking — every 5 min
        if now - last["parking"] >= INTERVALS["parking"]:
            produce_parkings(producer)
            last["parking"] = now

        # TAM — every 30 sec
        if now - last["tam"] >= INTERVALS["tam"]:
            produce_tam(producer)
            last["tam"] = now

        # Meteo — every 1 hour
        if now - last["meteo"] >= INTERVALS["meteo"]:
            produce_meteo(producer)
            last["meteo"] = now

        # AQI — every 1 hour
        if now - last["aqi"] >= INTERVALS["aqi"]:
            produce_aqi(producer)
            last["aqi"] = now

        time.sleep(10)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        log.info("Producer stopped.")

"""
MODALITY-FLOW — Kafka Consumer (confluent-kafka)
Reads messages from Kafka topics and writes to Railway PostgreSQL.

Usage:
    cd ~/Desktop/Velo
    python3 kafka_consumer.py
"""

import os
import json
import logging
import psycopg2
from datetime import datetime
from confluent_kafka import Consumer, KafkaError
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG -------------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVER = os.environ.get("KAFKA_BOOTSTRAP_SERVER", "localhost:9092")
KAFKA_API_KEY          = os.environ.get("KAFKA_API_KEY", "")
KAFKA_API_SECRET       = os.environ.get("KAFKA_API_SECRET", "")
CONSUMER_GROUP         = "modality-flow-consumer"

DB_URL = os.environ.get("DATABASE_PUBLIC_URL", "")

TOPICS = [
    "velomagg.station_status",
    "velomagg.free_bikes",
    "parking.status",
    "tam.trip_updates",
    "tam.vehicle_positions",
    "environnement.meteo",
    "environnement.aqi",
]

# --- LOGGING ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("kafka_consumer")


# --- DATABASE -----------------------------------------------------------------
def get_pg():
    return psycopg2.connect(DB_URL)


# --- HANDLERS -----------------------------------------------------------------
def handle_station_status(msg, cur):
    cur.execute("""
        INSERT INTO modality.fact_station_status
            (station_id, bikes_available, docks_available, is_renting, is_returning, timestamp, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        msg.get("station_id"),
        msg.get("bikes_available", 0),
        msg.get("docks_available", 0),
        msg.get("is_renting", False),
        msg.get("is_returning", False),
        msg.get("timestamp"),
        msg.get("source", "kafka")
    ))


def handle_free_bikes(msg, cur):
    cur.execute("""
        INSERT INTO modality.fact_free_bikes
            (bike_id, lat, lon, is_reserved, is_disabled, vehicle_type_id, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (bike_id) DO UPDATE SET
            lat           = EXCLUDED.lat,
            lon           = EXCLUDED.lon,
            is_reserved   = EXCLUDED.is_reserved,
            is_disabled   = EXCLUDED.is_disabled,
            timestamp     = EXCLUDED.timestamp
    """, (
        msg.get("bike_id"),
        msg.get("lat", 0),
        msg.get("lon", 0),
        msg.get("is_reserved", False),
        msg.get("is_disabled", False),
        msg.get("vehicle_type_id", ""),
        msg.get("timestamp")
    ))


def handle_parking(msg, cur):
    cur.execute("""
        INSERT INTO modality.fact_parkings_status
            (parking_id, free_spots, total_spots, taux_occupation, status, lat, lon, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        msg.get("parking_id"),
        msg.get("free_spots", 0),
        msg.get("total_spots", 0),
        msg.get("taux_occupation", 0),
        msg.get("status", "unknown"),
        msg.get("lat", 0),
        msg.get("lon", 0),
        msg.get("timestamp")
    ))


def handle_meteo(msg, cur):
    today = datetime.now().date().isoformat()
    cur.execute("""
        INSERT INTO public.dim_meteo
            (date, temperature_max, precipitation_sum, wind_speed_max, weather_code)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (date) DO UPDATE SET
            temperature_max   = EXCLUDED.temperature_max,
            precipitation_sum = EXCLUDED.precipitation_sum,
            wind_speed_max    = EXCLUDED.wind_speed_max,
            weather_code      = EXCLUDED.weather_code
    """, (
        today,
        msg.get("temperature"),
        msg.get("precipitation"),
        msg.get("wind_speed"),
        msg.get("weather_code")
    ))


def handle_aqi(msg, cur):
    today = datetime.now().date().isoformat()
    pm10 = msg.get("pm10") or 0
    o3   = msg.get("o3")   or 0
    no2  = msg.get("no2")  or 0

    # Compute indice_qualite from pollutants (simplified ATMO scale 1-6)
    if pm10 <= 10 and o3 <= 50 and no2 <= 25:
        indice = 1
    elif pm10 <= 20 and o3 <= 80 and no2 <= 50:
        indice = 2
    elif pm10 <= 30 and o3 <= 120 and no2 <= 100:
        indice = 3
    elif pm10 <= 50 and o3 <= 160 and no2 <= 150:
        indice = 4
    elif pm10 <= 80 and o3 <= 200 and no2 <= 200:
        indice = 5
    else:
        indice = 6

    cur.execute("""
        INSERT INTO public.dim_qualite_air
            (date, indice_qualite, pm10, pm25, no2, o3)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (date) DO UPDATE SET
            indice_qualite = EXCLUDED.indice_qualite,
            pm10 = EXCLUDED.pm10,
            pm25 = EXCLUDED.pm25,
            no2  = EXCLUDED.no2,
            o3   = EXCLUDED.o3
    """, (
        today,
        indice,
        msg.get("pm10"),
        msg.get("pm25"),
        msg.get("no2"),
        msg.get("o3")
    ))


def handle_tam(msg, cur):
    log.info(f"  TAM message received: {msg.get('size_bytes', 0)} bytes")


# --- TOPIC ROUTER -------------------------------------------------------------
HANDLERS = {
    "velomagg.station_status": handle_station_status,
    "velomagg.free_bikes":     handle_free_bikes,
    "parking.status":          handle_parking,
    "tam.trip_updates":        handle_tam,
    "tam.vehicle_positions":   handle_tam,
    "environnement.meteo":     handle_meteo,
    "environnement.aqi":       handle_aqi,
}


# --- MAIN LOOP ----------------------------------------------------------------
def run():
    log.info("MODALITY-FLOW Kafka Consumer starting...")

    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVER,
        "group.id":          CONSUMER_GROUP,
        "auto.offset.reset": "latest",
    }
    if KAFKA_API_KEY and KAFKA_API_SECRET:
        conf.update({
            "security.protocol": "SASL_SSL",
            "sasl.mechanism":    "PLAIN",
            "sasl.username":     KAFKA_API_KEY,
            "sasl.password":     KAFKA_API_SECRET,
        })
    consumer = Consumer(conf)
    consumer.subscribe(TOPICS)
    log.info(f"  Subscribed to {TOPICS}")

    conn = get_pg()
    cur  = conn.cursor()

    counters = {t: 0 for t in TOPICS}

    try:
        while True:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                log.error(f"Kafka error: {msg.error()}")
                continue

            topic   = msg.topic()
            payload = json.loads(msg.value())
            handler = HANDLERS.get(topic)

            if handler:
                try:
                    handler(payload, cur)
                    conn.commit()
                    counters[topic] += 1

                    if counters[topic] % 50 == 0:
                        log.info(f"  [{topic}] {counters[topic]} messages processed")

                except Exception as e:
                    log.error(f"  Error on {topic}: {e}")
                    conn.rollback()

    except KeyboardInterrupt:
        log.info("Consumer stopped.")
    finally:
        cur.close()
        conn.close()
        consumer.close()
        log.info("Final stats:")
        for topic, count in counters.items():
            if count > 0:
                log.info(f"  {topic}: {count} messages")


if __name__ == "__main__":
    run()

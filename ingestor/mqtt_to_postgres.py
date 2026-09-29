"""Ingestor: subscribes to MQTT telemetry topics and batch-inserts into PostgreSQL."""
import atexit
import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ingestor")

# --- config ---
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC_PATTERN", "factory/+/+/telemetry")
PG_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("POSTGRES_DB", "iot_telemetry")
PG_USER = os.getenv("POSTGRES_USER", "iot")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "iotpass")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
FLUSH_INTERVAL = float(os.getenv("FLUSH_INTERVAL", "2.0"))

INSERT_SQL = """
INSERT INTO telemetry (device_id, recorded_at, voltage_v, current_a, power_kw, temperature_c)
VALUES %s
"""

REQUIRED_FIELDS = {"device_id", "timestamp", "voltage_v", "current_a", "power_kw", "temperature_c"}

# ---- state ----
buffer = []
buffer_lock = threading.Lock()
db_conn = None
shutting_down = False


def get_db_connection():
    """Connect (or reconnect) to PostgreSQL."""
    global db_conn
    try:
        if db_conn and not db_conn.closed:
            db_conn.close()
    except Exception:
        pass
    db_conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS,
    )
    db_conn.autocommit = False
    log.info("connected to PostgreSQL %s:%d/%s", PG_HOST, PG_PORT, PG_DB)
    return db_conn


def flush():
    """Write buffered rows to the database."""
    global db_conn
    with buffer_lock:
        if not buffer:
            return
        batch = list(buffer)
        buffer.clear()

    for attempt in range(3):
        try:
            if db_conn is None or db_conn.closed:
                db_conn = get_db_connection()
            cur = db_conn.cursor()
            execute_values(cur, INSERT_SQL, batch)
            db_conn.commit()
            log.info("flushed %d rows", len(batch))
            return
        except psycopg2.Error as e:
            log.error("DB write failed (attempt %d): %s", attempt + 1, e)
            db_conn = None
            time.sleep(1)

    # All retries failed -- put rows back so we don't lose them silently
    log.error("giving up on batch of %d rows, re-queuing", len(batch))
    with buffer_lock:
        buffer[:0] = batch


def periodic_flusher():
    """Runs in a background thread, flushes on a timer."""
    while not shutting_down:
        time.sleep(FLUSH_INTERVAL)
        flush()


def validate(payload):
    if not isinstance(payload, dict):
        return False
    if not REQUIRED_FIELDS.issubset(payload.keys()):
        return False
    try:
        datetime.fromisoformat(payload["timestamp"])
        float(payload["voltage_v"])
        float(payload["current_a"])
        float(payload["power_kw"])
        float(payload["temperature_c"])
    except (ValueError, TypeError):
        return False
    return True


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("MQTT connected, subscribing to %s", MQTT_TOPIC)
        client.subscribe(MQTT_TOPIC, qos=1)
    else:
        log.warning("MQTT connect failed, rc=%d", rc)


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
    except json.JSONDecodeError:
        log.warning("malformed JSON on %s, skipping", msg.topic)
        return

    if not validate(payload):
        log.warning("invalid payload on %s: %s", msg.topic, msg.payload[:200])
        return

    row = (
        payload["device_id"],
        payload["timestamp"],
        float(payload["voltage_v"]),
        float(payload["current_a"]),
        float(payload["power_kw"]),
        float(payload["temperature_c"]),
    )
    with buffer_lock:
        buffer.append(row)
        if len(buffer) >= BATCH_SIZE:
            # flush inline when batch is full
            threading.Thread(target=flush, daemon=True).start()


def shutdown(signum=None, frame=None):
    global shutting_down
    log.info("shutting down, flushing remaining buffer...")
    shutting_down = True
    flush()
    sys.exit(0)


def main():
    global db_conn

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    atexit.register(flush)

    # Connect to Postgres early so we fail fast on bad credentials
    db_conn = get_db_connection()

    mqc = mqtt.Client(client_id="ingestor-01", clean_session=False)
    mqc.on_connect = on_connect
    mqc.on_message = on_message
    mqc.reconnect_delay_set(min_delay=1, max_delay=30)

    log.info("connecting to MQTT broker at %s:%d", MQTT_HOST, MQTT_PORT)
    mqc.connect(MQTT_HOST, MQTT_PORT)

    flusher = threading.Thread(target=periodic_flusher, daemon=True)
    flusher.start()

    # loop_forever handles reconnects internally
    mqc.loop_forever()


if __name__ == "__main__":
    main()

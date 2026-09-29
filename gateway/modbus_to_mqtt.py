"""Gateway: polls Modbus registers and publishes telemetry to MQTT."""
import json
import logging
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("gateway")

# --- config ---
MODBUS_HOST = os.getenv("MODBUS_HOST", "127.0.0.1")
MODBUS_PORT = int(os.getenv("MODBUS_PORT", "5020"))
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "factory/line1/device01/telemetry")
DEVICE_ID = os.getenv("DEVICE_ID", "device01")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))


def make_mqtt_client():
    client = mqtt.Client(client_id="gateway-01", clean_session=True)

    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            log.info("MQTT connected to %s:%d", MQTT_HOST, MQTT_PORT)
        else:
            log.warning("MQTT connect failed, rc=%d", rc)

    def on_disconnect(c, userdata, rc):
        if rc != 0:
            log.warning("MQTT disconnected unexpectedly, will reconnect")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


def connect_modbus():
    client = ModbusTcpClient(host=MODBUS_HOST, port=MODBUS_PORT, timeout=5)
    if not client.connect():
        raise ConnectionError(f"cannot reach Modbus server at {MODBUS_HOST}:{MODBUS_PORT}")
    log.info("Modbus connected to %s:%d", MODBUS_HOST, MODBUS_PORT)
    return client


def read_registers(mb_client):
    result = mb_client.read_holding_registers(address=0, count=4, slave=1)
    if result.isError():
        raise IOError(f"Modbus read error: {result}")
    regs = result.registers
    return {
        "device_id": DEVICE_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "voltage_v": regs[0] / 10.0,
        "current_a": regs[1] / 100.0,
        "power_kw": regs[2] / 100.0,
        "temperature_c": regs[3] / 10.0,
    }


def main():
    mqc = make_mqtt_client()
    mqc.connect(MQTT_HOST, MQTT_PORT)
    mqc.loop_start()

    mb = None

    try:
        while True:
            # (re)connect Modbus if needed
            if mb is None or not mb.is_socket_open():
                try:
                    if mb:
                        mb.close()
                    mb = connect_modbus()
                except Exception as e:
                    log.error("Modbus connect failed: %s, retrying in 3s", e)
                    time.sleep(3)
                    continue

            try:
                payload = read_registers(mb)
            except Exception as e:
                log.error("Modbus read failed: %s", e)
                mb.close()
                mb = None
                time.sleep(1)
                continue

            msg = json.dumps(payload)
            info = mqc.publish(MQTT_TOPIC, msg, qos=1)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                log.warning("MQTT publish failed, rc=%d", info.rc)
            else:
                log.info(
                    "V=%.1f I=%.2f P=%.2f T=%.1f -> %s",
                    payload["voltage_v"], payload["current_a"],
                    payload["power_kw"], payload["temperature_c"],
                    MQTT_TOPIC,
                )

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        if mb:
            mb.close()
        mqc.loop_stop()
        mqc.disconnect()


if __name__ == "__main__":
    main()

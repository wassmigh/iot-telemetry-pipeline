"""Modbus TCP server that replays CSV telemetry data through holding registers.

Register map (all 16-bit unsigned):
  0  voltage    V x 10
  1  current    A x 100
  2  power      kW x 100
  3  temperature C x 10
"""
import csv
import logging
import os
import sys
import threading
import time

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartTcpServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("modbus_sim")

MODBUS_HOST = os.getenv("MODBUS_HOST", "0.0.0.0")
MODBUS_PORT = int(os.getenv("MODBUS_PORT", "5020"))
CSV_PATH = os.getenv("CSV_PATH", "data/sample.csv")


def load_csv(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "voltage": float(row["voltage"]),
                "current": float(row["current"]),
                "power": float(row["power"]),
                "temperature": float(row["temperature"]),
            })
    if not rows:
        log.error("CSV is empty: %s", path)
        sys.exit(1)
    return rows


def scale_row(row):
    """Convert floats to scaled 16-bit integers for Modbus registers."""
    return [
        int(round(row["voltage"] * 10)),
        int(round(row["current"] * 100)),
        int(round(row["power"] * 100)),
        int(round(row["temperature"] * 10)),
    ]


def updater(context, data, interval=1.0):
    """Background thread: write one CSV row to holding registers per tick."""
    idx = 0
    slave_ctx = context[0x00]
    while True:
        row = data[idx % len(data)]
        values = scale_row(row)
        slave_ctx.setValues(3, 0, values)  # fc=3 -> holding registers
        if idx % 60 == 0:
            log.info(
                "row %d/%d  V=%.1f  I=%.1f  P=%.3f  T=%.1f",
                idx % len(data), len(data),
                row["voltage"], row["current"], row["power"], row["temperature"],
            )
        idx += 1
        time.sleep(interval)


def main():
    data = load_csv(CSV_PATH)
    log.info("loaded %d rows from %s", len(data), CSV_PATH)

    # Pre-fill registers with the first row
    initial = scale_row(data[0])
    block = ModbusSequentialDataBlock(0, initial + [0] * 96)
    store = ModbusSlaveContext(hr=block, zero_mode=True)
    context = ModbusServerContext(slaves=store, single=True)

    t = threading.Thread(target=updater, args=(context, data), daemon=True)
    t.start()

    log.info("starting Modbus TCP server on %s:%d", MODBUS_HOST, MODBUS_PORT)
    StartTcpServer(context=context, address=(MODBUS_HOST, MODBUS_PORT))


if __name__ == "__main__":
    main()

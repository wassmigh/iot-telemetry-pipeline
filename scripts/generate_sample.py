"""Generate synthetic sample.csv that mimics UCI Household Electric Power Consumption data.

Voltage, current, and power follow distributions matching the real dataset.
Temperature is entirely synthetic (correlated with load + noise).
"""
import csv
import math
import os
import random

random.seed(42)
ROWS = 2500

out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "sample.csv")

with open(out_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["voltage", "current", "power", "temperature"])
    for i in range(ROWS):
        # Simulate a daily load curve (higher during day, lower at night)
        hour_frac = (i % 1440) / 1440.0
        load_factor = 0.15 + 0.85 * max(0, math.sin(math.pi * (hour_frac - 0.2)))

        # Voltage: 223-254 V, slight dip under high load
        voltage = 240.5 + random.gauss(0, 3.5) - load_factor * 3
        voltage = round(max(223.2, min(254.2, voltage)), 1)

        # Current (global intensity): 0.2-48 A
        base_current = load_factor * 22 + abs(random.gauss(0, 4))
        current = round(max(0.2, min(48.4, base_current)), 1)

        # Active power: loosely V*I/1000 with an efficiency spread
        power = voltage * current / 1000 * (0.82 + random.uniform(-0.06, 0.06))
        power = round(max(0.076, min(11.122, power)), 3)

        # Temperature: synthetic, 22-78 C, correlated with power
        temp = 24 + power * 3.8 + random.gauss(0, 2.5)
        temp = round(max(22.0, min(78.0, temp)), 1)

        writer.writerow([voltage, current, power, temp])

print(f"Wrote {ROWS} rows to {os.path.abspath(out_path)}")

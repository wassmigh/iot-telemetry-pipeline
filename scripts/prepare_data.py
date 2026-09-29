"""Prepare sample.csv from the UCI Individual Household Electric Power Consumption dataset.

Download the original from:
  https://archive.ics.uci.edu/ml/datasets/Individual+household+electric+power+consumption

Expected input file: household_power_consumption.txt (semicolon-separated, ~2M rows).

This script:
  1. Reads voltage, Global_intensity (current), and Global_active_power.
  2. Drops rows with missing values (marked as '?').
  3. Samples ~2500 rows spread across the dataset.
  4. Adds a synthetic temperature column: base temp + load-correlated component + noise.
  5. Writes data/sample.csv.

Temperature is NOT from the original dataset. It is generated to roughly simulate
equipment temperature that rises with electrical load.
"""
import csv
import math
import os
import random
import sys

random.seed(42)
TARGET_ROWS = 2500
STEP = None  # computed after loading

INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "household_power_consumption.txt"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "sample.csv")


def parse_row(parts):
    """Return (voltage, current, power) or None if any field is missing."""
    try:
        voltage = float(parts[4])        # Voltage
        current = float(parts[6])        # Global_intensity
        power = float(parts[2])          # Global_active_power
    except (ValueError, IndexError):
        return None
    return voltage, current, power


def synthetic_temperature(power):
    """Equipment temp: baseline 24 C, increases ~4 C per kW, with noise."""
    return round(24.0 + power * 3.8 + random.gauss(0, 2.5), 1)


def main():
    if not os.path.isfile(INPUT_FILE):
        print(f"Input file not found: {INPUT_FILE}")
        print("Download household_power_consumption.txt from the UCI ML Repository")
        print("and place it in the current directory, or pass its path as an argument.")
        sys.exit(1)

    # First pass: count usable rows
    raw = []
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)  # skip header
        for parts in reader:
            parsed = parse_row(parts)
            if parsed:
                raw.append(parsed)

    print(f"loaded {len(raw)} valid rows from {INPUT_FILE}")

    # Evenly sample TARGET_ROWS rows
    step = max(1, len(raw) // TARGET_ROWS)
    sampled = raw[::step][:TARGET_ROWS]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["voltage", "current", "power", "temperature"])
        for voltage, current, power in sampled:
            temp = synthetic_temperature(power)
            writer.writerow([
                round(voltage, 1),
                round(current, 1),
                round(power, 3),
                temp,
            ])

    print(f"wrote {len(sampled)} rows to {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    main()

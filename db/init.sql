-- Schema for IoT telemetry storage

CREATE TABLE IF NOT EXISTS devices (
    device_id   VARCHAR(64) PRIMARY KEY,
    location    VARCHAR(128),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS telemetry (
    id              BIGSERIAL PRIMARY KEY,
    device_id       VARCHAR(64) NOT NULL REFERENCES devices(device_id),
    recorded_at     TIMESTAMPTZ NOT NULL,
    voltage_v       DOUBLE PRECISION,
    current_a       DOUBLE PRECISION,
    power_kw        DOUBLE PRECISION,
    temperature_c   DOUBLE PRECISION,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
    ON telemetry (device_id, recorded_at DESC);

-- Seed a default device so FK inserts work out of the box.
INSERT INTO devices (device_id, location)
VALUES ('device01', 'factory/line1')
ON CONFLICT DO NOTHING;

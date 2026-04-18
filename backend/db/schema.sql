-- ============================================================
-- Bee With Me — PostgreSQL Schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------
-- Enums
-- ------------------------------------------------------------

CREATE TYPE app_role    AS ENUM ('admin', 'rescuer', 'viewer');
CREATE TYPE device_type AS ENUM ('bee', 'repeater');

-- ------------------------------------------------------------
-- Users
-- password_hash is NULL for field personnel with no app login
-- ------------------------------------------------------------

CREATE TABLE users (
    id             UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    username       VARCHAR(64)  UNIQUE,          -- NULL = field personnel with no app login
    password_hash  VARCHAR(255),
    pin            VARCHAR(20),                  -- identification number (plaintext)
    pin_hash       VARCHAR(255),                 -- legacy hashed PIN (kept for auth compat)
    first_name     VARCHAR(128) NOT NULL DEFAULT '',
    last_name      VARCHAR(128) NOT NULL DEFAULT '',
    full_name      VARCHAR(255) NOT NULL,        -- kept as first_name || ' ' || last_name
    email          VARCHAR(255),
    phone          VARCHAR(64)  NOT NULL DEFAULT '',
    rank           VARCHAR(64),
    blood_type     VARCHAR(5),
    photo_url      VARCHAR(500),
    notes          TEXT,
    is_radio_enthusiast BOOLEAN      NOT NULL DEFAULT FALSE,
    radio_initials      VARCHAR(20),
    role           app_role     NOT NULL DEFAULT 'viewer',
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Groups
-- color is a hex string used to tint map markers (#RRGGBB)
-- ------------------------------------------------------------

CREATE TABLE groups (
    id          UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         VARCHAR(255) UNIQUE NOT NULL,
    description  TEXT,
    organization VARCHAR(255),
    color        VARCHAR(7)   NOT NULL DEFAULT '#3388ff',
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- User ↔ Group membership
-- ------------------------------------------------------------

CREATE TABLE user_groups (
    user_id    UUID        NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    group_id   UUID        NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    is_leader  BOOLEAN     NOT NULL DEFAULT FALSE,
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, group_id)
);

-- ------------------------------------------------------------
-- Devices
-- dev_sn matches DevSN field from the serial protocol
-- ------------------------------------------------------------

CREATE TABLE devices (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    dev_sn      INTEGER     UNIQUE NOT NULL,
    name        VARCHAR(255),
    device_type device_type NOT NULL DEFAULT 'bee',
    user_id     UUID        REFERENCES users(id) ON DELETE SET NULL,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Location events  (Cmd = 30, RescuerBee)
-- Both raw lat/lng and PostGIS point are stored.
-- mgrs is pre-computed by the serial reader service.
-- ------------------------------------------------------------

CREATE TABLE location_events (
    id               BIGSERIAL    PRIMARY KEY,
    device_id        UUID         NOT NULL REFERENCES devices(id),
    user_id          UUID         REFERENCES users(id),  -- denormalised for fast queries
    msg_id           SMALLINT     NOT NULL,
    recorded_at      TIMESTAMPTZ  NOT NULL,              -- UTC from device fields
    received_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    position         GEOMETRY(Point, 4326) NOT NULL,
    latitude         DOUBLE PRECISION NOT NULL,
    longitude        DOUBLE PRECISION NOT NULL,
    mgrs             VARCHAR(20)  NOT NULL,
    altitude_m       SMALLINT,
    speed_knots      REAL,
    course_deg       SMALLINT,
    gnss_satellites  SMALLINT,
    battery_voltage  REAL,
    sos_active       BOOLEAN      NOT NULL DEFAULT FALSE,
    repeater_mode    BOOLEAN      NOT NULL DEFAULT FALSE,
    raw_flags        SMALLINT
);

-- ------------------------------------------------------------
-- Repeater events  (Cmd = 20, RescuerRepeater)
-- ------------------------------------------------------------

CREATE TABLE repeater_events (
    id              BIGSERIAL   PRIMARY KEY,
    device_id       UUID        NOT NULL REFERENCES devices(id),
    msg_id          SMALLINT    NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    battery_voltage REAL
);

-- ------------------------------------------------------------
-- SOS alerts
-- Created when sos_active flips TRUE, resolved manually.
-- ------------------------------------------------------------

CREATE TABLE sos_alerts (
    id           UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id    UUID        NOT NULL REFERENCES devices(id),
    user_id      UUID        REFERENCES users(id),
    triggered_at TIMESTAMPTZ NOT NULL,
    resolved_at  TIMESTAMPTZ,
    resolved_by  UUID        REFERENCES users(id),
    notes        TEXT
);

-- ------------------------------------------------------------
-- Indexes
-- ------------------------------------------------------------

CREATE INDEX idx_location_events_device_time  ON location_events (device_id, recorded_at DESC);
CREATE INDEX idx_location_events_user_time    ON location_events (user_id,   recorded_at DESC);
CREATE INDEX idx_location_events_sos          ON location_events (sos_active) WHERE sos_active = TRUE;
CREATE INDEX idx_location_events_position     ON location_events USING GIST (position);
CREATE INDEX idx_sos_alerts_open              ON sos_alerts (device_id) WHERE resolved_at IS NULL;

-- ------------------------------------------------------------
-- Auto-update updated_at
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_groups_updated_at
    BEFORE UPDATE ON groups
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

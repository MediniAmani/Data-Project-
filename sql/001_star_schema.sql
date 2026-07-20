-- Airport Authority star tables inside schema airport_authority
-- Target database: postgres (default main database)
--
-- Apply once (or re-apply to reset):
--   "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d postgres -f sql\001_star_schema.sql

BEGIN;

DROP SCHEMA IF EXISTS airport_authority CASCADE;
CREATE SCHEMA airport_authority;

CREATE TABLE airport_authority.dim_airline (
    airline_key   TEXT PRIMARY KEY,
    airline_name  TEXT NOT NULL
);

CREATE TABLE airport_authority.dim_date (
    date             DATE PRIMARY KEY,
    year             INTEGER NOT NULL,
    month            INTEGER NOT NULL,
    month_name       TEXT NOT NULL,
    quarter          INTEGER NOT NULL,
    week_of_year     INTEGER NOT NULL,
    day_of_week      INTEGER NOT NULL,
    day_of_week_name TEXT NOT NULL,
    is_weekend       BOOLEAN NOT NULL
);

CREATE TABLE airport_authority.dim_origin_airport (
    origin_airport_key TEXT PRIMARY KEY,
    origin_city        TEXT,
    origin_state       TEXT
);

CREATE TABLE airport_authority.dim_dest_airport (
    dest_airport_key TEXT PRIMARY KEY,
    dest_city        TEXT,
    dest_state       TEXT
);

CREATE TABLE airport_authority.dim_route (
    route_key          TEXT PRIMARY KEY,
    origin_airport_key TEXT NOT NULL REFERENCES airport_authority.dim_origin_airport (origin_airport_key),
    dest_airport_key   TEXT NOT NULL REFERENCES airport_authority.dim_dest_airport (dest_airport_key)
);

CREATE TABLE airport_authority.fact_flight_operations (
    flight_key          TEXT PRIMARY KEY,
    date                DATE NOT NULL REFERENCES airport_authority.dim_date (date),
    airline_key         TEXT NOT NULL REFERENCES airport_authority.dim_airline (airline_key),
    flight_number       TEXT,
    tail_number         TEXT,
    origin_airport_key  TEXT NOT NULL REFERENCES airport_authority.dim_origin_airport (origin_airport_key),
    dest_airport_key    TEXT NOT NULL REFERENCES airport_authority.dim_dest_airport (dest_airport_key),
    route_key           TEXT NOT NULL REFERENCES airport_authority.dim_route (route_key),
    hour_of_day         INTEGER,
    time_of_day_bank    TEXT,
    touches_home_as     TEXT,
    is_cancelled        BOOLEAN NOT NULL,
    cancellation_code   TEXT,
    is_diverted         BOOLEAN NOT NULL,
    dep_delay_minutes   DOUBLE PRECISION,
    arr_delay_minutes   DOUBLE PRECISION,
    is_dep_delayed      BOOLEAN,
    is_arr_delayed      BOOLEAN,
    is_on_time_arrival  BOOLEAN,
    delay_bucket        TEXT,
    distance            DOUBLE PRECISION,
    carrier_delay       DOUBLE PRECISION,
    weather_delay       DOUBLE PRECISION,
    nas_delay           DOUBLE PRECISION,
    security_delay      DOUBLE PRECISION,
    late_aircraft_delay DOUBLE PRECISION
);

CREATE TABLE airport_authority.fact_delay_cause_minutes (
    id                  BIGSERIAL PRIMARY KEY,
    flight_key          TEXT NOT NULL,
    date                DATE NOT NULL REFERENCES airport_authority.dim_date (date),
    airline_key         TEXT NOT NULL REFERENCES airport_authority.dim_airline (airline_key),
    cause_type          TEXT NOT NULL,
    delay_cause_minutes DOUBLE PRECISION NOT NULL
);

CREATE TABLE airport_authority.etl_run_log (
    run_id       BIGSERIAL PRIMARY KEY,
    ran_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_label TEXT NOT NULL,
    home_airport TEXT NOT NULL,
    fact_rows    INTEGER NOT NULL,
    cause_rows   INTEGER NOT NULL,
    date_min     DATE,
    date_max     DATE,
    notes        TEXT
);

CREATE INDEX ix_fact_ops_date ON airport_authority.fact_flight_operations (date);
CREATE INDEX ix_fact_ops_airline ON airport_authority.fact_flight_operations (airline_key);
CREATE INDEX ix_fact_ops_route ON airport_authority.fact_flight_operations (route_key);
CREATE INDEX ix_fact_cause_date ON airport_authority.fact_delay_cause_minutes (date);
CREATE INDEX ix_fact_cause_type ON airport_authority.fact_delay_cause_minutes (cause_type);

COMMIT;

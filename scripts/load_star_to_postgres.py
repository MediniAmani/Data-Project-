"""Load star-schema CSVs from data/star/ into local PostgreSQL.

Target:
  Database: postgres (default main DB)
  Schema:   airport_authority

Prerequisites:
  1. PostgreSQL installed and running (no Docker).
  2. db.env present (copy from db.env.example, set PGPASSWORD).
  3. Schema applied:
       psql -U postgres -d postgres -f sql/001_star_schema.sql

Run from airport-authority folder:
  python scripts/load_star_to_postgres.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
STAR_DIR = ROOT / "data" / "star"
ENV_PATH = ROOT / "db.env"

# CSV stem -> (table_name, column rename map CSV -> SQL)
TABLES: list[tuple[str, str, dict[str, str]]] = [
    (
        "DimAirline.csv",
        "dim_airline",
        {"AirlineKey": "airline_key", "AirlineName": "airline_name"},
    ),
    (
        "DimDate.csv",
        "dim_date",
        {
            "Date": "date",
            "Year": "year",
            "Month": "month",
            "MonthName": "month_name",
            "Quarter": "quarter",
            "WeekOfYear": "week_of_year",
            "DayOfWeek": "day_of_week",
            "DayOfWeekName": "day_of_week_name",
            "IsWeekend": "is_weekend",
        },
    ),
    (
        "DimOriginAirport.csv",
        "dim_origin_airport",
        {
            "OriginAirportKey": "origin_airport_key",
            "OriginCity": "origin_city",
            "OriginState": "origin_state",
        },
    ),
    (
        "DimDestAirport.csv",
        "dim_dest_airport",
        {
            "DestAirportKey": "dest_airport_key",
            "DestCity": "dest_city",
            "DestState": "dest_state",
        },
    ),
    (
        "DimRoute.csv",
        "dim_route",
        {
            "RouteKey": "route_key",
            "OriginAirportKey": "origin_airport_key",
            "DestAirportKey": "dest_airport_key",
        },
    ),
    (
        "FactFlightOperations.csv",
        "fact_flight_operations",
        {
            "FlightKey": "flight_key",
            "Date": "date",
            "AirlineKey": "airline_key",
            "FlightNumber": "flight_number",
            "TailNumber": "tail_number",
            "OriginAirportKey": "origin_airport_key",
            "DestAirportKey": "dest_airport_key",
            "RouteKey": "route_key",
            "HourOfDay": "hour_of_day",
            "TimeOfDayBank": "time_of_day_bank",
            "TouchesHomeAs": "touches_home_as",
            "IsCancelled": "is_cancelled",
            "CancellationCode": "cancellation_code",
            "IsDiverted": "is_diverted",
            "DepDelayMinutes": "dep_delay_minutes",
            "ArrDelayMinutes": "arr_delay_minutes",
            "IsDepDelayed": "is_dep_delayed",
            "IsArrDelayed": "is_arr_delayed",
            "IsOnTimeArrival": "is_on_time_arrival",
            "DelayBucket": "delay_bucket",
            "Distance": "distance",
            "CarrierDelay": "carrier_delay",
            "WeatherDelay": "weather_delay",
            "NASDelay": "nas_delay",
            "SecurityDelay": "security_delay",
            "LateAircraftDelay": "late_aircraft_delay",
        },
    ),
    (
        "FactDelayCauseMinutes.csv",
        "fact_delay_cause_minutes",
        {
            "FlightKey": "flight_key",
            "Date": "date",
            "AirlineKey": "airline_key",
            "CauseType": "cause_type",
            "DelayCauseMinutes": "delay_cause_minutes",
        },
    ),
]

TRUNCATE_ORDER = [
    "fact_delay_cause_minutes",
    "fact_flight_operations",
    "dim_route",
    "dim_dest_airport",
    "dim_origin_airport",
    "dim_airline",
    "dim_date",
]


def load_db_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(
            f"Missing {path}. Copy db.env.example to db.env and set your local Postgres password."
        )
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip().strip('"').strip("'")
    required = ["PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE", "PGSCHEMA"]
    missing = [k for k in required if not values.get(k)]
    if missing:
        raise SystemExit(f"db.env missing required keys: {', '.join(missing)}")
    return values


def connect(cfg: dict[str, str]) -> psycopg.Connection:
    conn = psycopg.connect(
        host=cfg["PGHOST"],
        port=int(cfg["PGPORT"]),
        user=cfg["PGUSER"],
        password=cfg["PGPASSWORD"],
        dbname=cfg["PGDATABASE"],
    )
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SET search_path TO {}, public").format(sql.Identifier(cfg["PGSCHEMA"]))
        )
    conn.commit()
    return conn


def read_star_csv(csv_name: str, rename: dict[str, str]) -> pd.DataFrame:
    path = STAR_DIR / csv_name
    if not path.is_file():
        raise SystemExit(f"Missing star file: {path}. Run build_star_schema.py first.")
    df = pd.read_csv(path)
    missing_cols = [c for c in rename if c not in df.columns]
    if missing_cols:
        raise SystemExit(f"{csv_name} missing columns: {missing_cols}")
    df = df.rename(columns=rename)
    return df[list(rename.values())]


def qualified(schema: str, table: str) -> sql.Composed:
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))


def copy_dataframe(cur: psycopg.Cursor, schema: str, table: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = list(df.columns)
    col_list = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
    copy_sql = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)").format(
        qualified(schema, table),
        col_list,
    )
    buf = df.to_csv(index=False)
    with cur.copy(copy_sql) as copy:
        copy.write(buf.encode("utf-8"))
    return len(df)


def main() -> None:
    cfg = load_db_env(ENV_PATH)
    schema = cfg["PGSCHEMA"]
    print(f"loading star CSVs from {STAR_DIR}")
    print(
        f"target: {cfg['PGUSER']}@{cfg['PGHOST']}:{cfg['PGPORT']}/"
        f"{cfg['PGDATABASE']}.{schema}"
    )

    frames: dict[str, pd.DataFrame] = {}
    for csv_name, table, rename in TABLES:
        frames[table] = read_star_csv(csv_name, rename)
        print(f"  prepared {table}: {len(frames[table]):,} rows")

    with connect(cfg) as conn:
        with conn.cursor() as cur:
            for table in TRUNCATE_ORDER:
                cur.execute(
                    sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                        qualified(schema, table)
                    )
                )
            print("truncated done")

            load_order = [
                "dim_airline",
                "dim_date",
                "dim_origin_airport",
                "dim_dest_airport",
                "dim_route",
                "fact_flight_operations",
                "fact_delay_cause_minutes",
            ]
            counts: dict[str, int] = {}
            for table in load_order:
                n = copy_dataframe(cur, schema, table, frames[table])
                counts[table] = n
                print(f"  loaded {table}: {n:,}")

            fact = frames["fact_flight_operations"]
            cur.execute(
                sql.SQL(
                    """
                    INSERT INTO {} (
                        source_label, home_airport, fact_rows, cause_rows,
                        date_min, date_max, notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                ).format(qualified(schema, "etl_run_log")),
                (
                    "data/star CSV reload",
                    "ATL",
                    counts["fact_flight_operations"],
                    counts["fact_delay_cause_minutes"],
                    pd.to_datetime(fact["date"]).min().date() if len(fact) else None,
                    pd.to_datetime(fact["date"]).max().date() if len(fact) else None,
                    "load_star_to_postgres.py",
                ),
            )
        conn.commit()

    print(
        f"done. Power BI: Get data → PostgreSQL → database postgres → schema {schema}"
    )


if __name__ == "__main__":
    os.environ.setdefault("PAGER", "cat")
    try:
        main()
    except psycopg.Error as e:
        print(f"Postgres error: {e}", file=sys.stderr)
        sys.exit(1)

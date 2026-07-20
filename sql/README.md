# Local PostgreSQL setup (no Docker)

## Layout

- **Database:** `postgres` (default main database)
- **Schema:** `airport_authority` (all star tables live here)

```text
BTS zips → build_star_schema.py → data/star/*.csv → load_star_to_postgres.py → postgres.airport_authority → Power BI
```

## One-time setup

1. Copy connection file:

```powershell
cd "c:\Amenis cv\power-bi-capstone\airport-authority"
copy db.env.example db.env
```

2. Edit `db.env` and set `PGPASSWORD` to your Postgres install password.

3. Create the schema and tables:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d postgres -f sql\001_star_schema.sql
```

This runs `CREATE SCHEMA airport_authority` inside database `postgres`, then creates `dim_*` / `fact_*` tables under that schema.

## Load data

```powershell
cd "c:\Amenis cv\power-bi-capstone\airport-authority"
.\.venv\Scripts\activate
python scripts/build_star_schema.py
python scripts/load_star_to_postgres.py
```

## Power BI

1. Get data → PostgreSQL database
2. Server: `localhost`
3. Database: `postgres`
4. Expand schema **`airport_authority`** and load `dim_*` / `fact_*`
5. Relationships:

| From | To |
|------|-----|
| dim_date[date] | fact_flight_operations[date] |
| dim_airline[airline_key] | fact_flight_operations[airline_key] |
| dim_origin_airport[origin_airport_key] | fact_flight_operations[origin_airport_key] |
| dim_dest_airport[dest_airport_key] | fact_flight_operations[dest_airport_key] |
| dim_route[route_key] | fact_flight_operations[route_key] |
| dim_date[date] | fact_delay_cause_minutes[date] |
| dim_airline[airline_key] | fact_delay_cause_minutes[airline_key] |

6. Mark `dim_date` as the date table.

## Tables (schema `airport_authority`)

| Table | Role |
|-------|------|
| dim_airline | Airlines |
| dim_date | Calendar |
| dim_origin_airport / dim_dest_airport | Airports |
| dim_route | Routes |
| fact_flight_operations | Flight grain |
| fact_delay_cause_minutes | Delay causes (unpivoted) |
| etl_run_log | Load audit |

## Note

`db.env` is gitignored. Do not commit passwords.

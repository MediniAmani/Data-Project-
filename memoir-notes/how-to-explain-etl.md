# ETL approach: from BTS files to a Power BI model

This note documents how raw BTS on-time data becomes the analytical model used in Power BI. It is a description of the method, not a presentation script.

## Purpose of the pipeline

The goal is to answer operational questions for an airport authority at **ATL**: when delays spike, which airlines, routes, and time windows matter most. The source data is national. The pipeline therefore has to **scope**, **clean**, **structure**, and **serve** only the flights that touch Atlanta, with rules that stay stable between rebuilds.

The path is:

```text
BTS monthly zips
  → build_star_schema.py   (extract, scope, clean, star model)
  → data/star/*.csv        (auditable intermediate export)
  → load_star_to_postgres.py
  → PostgreSQL (database postgres, schema airport_authority)
  → Power BI (Import mode)
```

`build_star_schema.py` owns transform logic. `load_star_to_postgres.py` loads the curated star into the warehouse. Power BI consumes the warehouse; it does not redefine grain or delay rules.

## Source and scope

- **Source:** US Bureau of Transportation Statistics, Airline On-Time Performance (Reporting Carrier), monthly PREZIP files for **2025**.
- **Home airport:** ATL. A flight is kept if origin or destination is ATL.
- **Period:** 2025-01-01 to 2025-12-31 (twelve monthly files required before a build is allowed).
- **Feedback path:** Path B (operational quality proxies). No synthetic passenger survey scores.

After stacking all months, the national extract is about **7.0 million** rows. After the ATL filter, **628,872** rows remain. Those become the fact grain. Figures are recorded in `data/dictionary/quality-metrics.json`.

## Role of `build_star_schema.py`

The script is the reproducible equivalent of a heavy Power Query stage. It does not download files. It reads the twelve monthly zips already stored under `data/raw/bts_monthly/`, applies locked business rules, and writes star tables plus a quality snapshot.

### Locked parameters

| Parameter | Value | Meaning |
|-----------|--------|---------|
| `HOME_AIRPORT` | `ATL` | Authority perimeter |
| `DELAY_THRESHOLD_MIN` | `15` | Industry-style on-time cutoff (minutes) |
| `YEAR` | `2025` | Build year; all twelve months must exist |

Carrier codes are mapped to display names through `AIRLINE_NAMES` (for example `DL` → Delta Air Lines).

### Supporting functions

| Function | Role |
|----------|------|
| `find_monthly_zips` | Locates the twelve monthly zips; exits if the set is incomplete |
| `load_bts_month` | Opens each zip, finds the CSV, reads only the required columns |
| `parse_hhmm` | Converts BTS integer times (for example `1455`) into hour-of-day |
| `delay_bucket` | Assigns arrival severity: On time, 15-45, 45-120, 120+, Cancelled, Unknown |
| `time_bank` | Groups departure hour into Night, Morning, Afternoon, Evening |

### Processing sequence in `main()`

1. **Load.** Concatenate the twelve monthly extracts into one frame.
2. **Scope.** Keep ATL origin or destination only.
3. **Normalize.** Parse dates; standardize airline, airport, and flight number fields; cast cancelled/diverted and delay minutes.
4. **Apply cancel rule.** Cancelled flights stay in the table for cancellation rates, but delay minutes are set to null so averages are not distorted.
5. **Derive flags.** Build `IsDepDelayed`, `IsArrDelayed`, and `IsOnTimeArrival` from the 15-minute rule.
6. **Enrich.** Add delay buckets, hour of day, time bank, `RouteKey`, `FlightKey`, and `TouchesHomeAs` (Origin / Dest / Both).
7. **Deduplicate.** Drop duplicate `FlightKey` values (carrier + date + flight number + origin + destination).
8. **Split the star.** Build dimension tables (airline, date, origin/dest airports, route) and fact tables (flight operations; unpivoted delay causes).
9. **Export.** Write CSVs under `data/star/` and write `quality-metrics.json`.

## Grain and business rules

**Grain (frozen):** one row in `FactFlightOperations` is one scheduled flight occurrence (carrier + flight date + flight number + origin + destination) that touches ATL, after deduplication.

**Rules locked for this build:**

1. Cancelled flights count toward cancellation rate; their delay minutes are null.
2. Delayed means delay minutes greater than 15.
3. On-time arrival means not cancelled and arrival delay minutes less than or equal to 15.
4. Delay buckets: On time / 15-45 / 45-120 / 120+ / Cancelled / Unknown.
5. Time banks from scheduled departure hour: Night before 6, Morning before 12, Afternoon before 18, Evening otherwise.

## Intermediate files and warehouse

The star CSVs under `data/star/` are an explicit checkpoint: same columns the warehouse receives, inspectable without a database connection.

`sql/001_star_schema.sql` creates schema `airport_authority` inside the default PostgreSQL database `postgres`, with dimension and fact tables, foreign keys, and indexes.

`load_star_to_postgres.py` truncates those tables and loads from the star CSVs (dims first, then facts), then writes a row to `etl_run_log`. Connection settings live in `db.env` (see `db.env.example`). Setup detail is in `sql/README.md`.

Power BI connects to `localhost`, database `postgres`, schema `airport_authority`, then defines relationships and DAX. Column and grain definitions stay upstream.

## Why this layering

| Choice | Rationale |
|--------|-----------|
| Python for transform | Full-year national files are large; filtering and rules stay versioned in code |
| CSV star export | Auditable intermediate; rebuilds can be checked before load |
| PostgreSQL middle layer | Stable serving model for BI; documents a warehouse step in the method |
| Power BI last | Visualization and measures only; avoids burying business rules in the report |

## Quality snapshot (ATL, 2025)

| Metric | Value |
|--------|-------|
| Raw rows (stacked national months) | 7,001,619 |
| Rows after ATL scope | 628,872 |
| Fact rows | 628,872 |
| Date coverage | 2025-01-01 to 2025-12-31 |
| Cancellation rate | 1.48% |
| Arrival delay rate (non-cancel, >15 min) | 20.69% |
| OTP (non-cancel, ArrDelay <= 15) | 79.03% |
| Airlines | 12 |
| Routes | 301 |
| Delay-cause rows (>0 minutes) | 212,038 |

Authoritative file: `data/dictionary/quality-metrics.json`.

## Related artifacts

| Path | Role |
|------|------|
| `scripts/download_bts_range.py` | Download monthly BTS zips |
| `scripts/build_star_schema.py` | Transform to star schema |
| `scripts/load_star_to_postgres.py` | Load star CSVs into PostgreSQL |
| `sql/001_star_schema.sql` | Schema and table definitions |
| `sql/README.md` | Local Postgres setup |
| `data/raw/bts_monthly/` | Source zips |
| `data/star/` | Intermediate star CSVs |
| `data/dictionary/quality-metrics.json` | Latest quality metrics |
| `measures/measures.md` | DAX measures after model load |
| `report/page-checklist.md` | Report page structure |

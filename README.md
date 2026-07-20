# Airport Authority Data Analysis

End-of-formation Power BI subject (primary).

**DATA QUESTION:** When delays spike, which airlines, routes, and time windows should ops prioritize, and does passenger feedback move with those failures?

**Scope locked for this build:**

- Home airport authority: **ATL** (Hartsfield-Jackson Atlanta International)
- Period: **full year 2025**
- Source: US BTS Airline On-Time Performance (Reporting Carrier)
- Feedback: **Path B** (ops quality proxies). No synthetic passenger scores.

## Pipeline

```text
BTS monthly zips
  → notebooks/02_build_star_schema.ipynb  (or scripts/build_star_schema.py)
  → data/star/*.csv
  → notebooks/03_load_star_to_postgres.ipynb  (or scripts/load_star_to_postgres.py)
  → local PostgreSQL database postgres / schema airport_authority
  → Power BI Desktop
```

### Jupyter notebooks (recommended for formation walkthrough)

| Notebook | Role |
|----------|------|
| `notebooks/01_download_bts_range.ipynb` | Download BTS monthly zips |
| `notebooks/02_build_star_schema.ipynb` | Transform → star CSVs + quality metrics |
| `notebooks/03_load_star_to_postgres.ipynb` | Load star CSVs into PostgreSQL |

Open notebooks with the project `.venv` kernel. Paths resolve whether the kernel cwd is `airport-authority/` or `notebooks/`.

Equivalent CLI scripts remain in `scripts/` if you prefer:

```powershell
cd "c:\Amenis cv\power-bi-capstone\airport-authority"
.\.venv\Scripts\activate
python scripts/build_star_schema.py
python scripts/load_star_to_postgres.py
```

CSV star files remain useful as a backup export. PostgreSQL is the middle warehouse for the formation story. Large fact CSVs are gitignored; rebuild them with the build notebook (or `python scripts/build_star_schema.py`) after cloning.

Postgres setup (local install, no Docker): see `sql/README.md`.

---

## What is already done

1. Downloaded BTS 2025 monthly zips into `data/raw/bts_monthly/`
2. Filtered to flights touching ATL (**628,872** flight rows)
3. Built star schema CSVs in `data/star/`
4. Wrote quality metrics, measure dictionary, report checklist, and Postgres schema/load scripts

## Load into Power BI

### Option A: PostgreSQL (preferred for architecture story)

1. Finish one-time setup in `sql/README.md`
2. Run `notebooks/03_load_star_to_postgres.ipynb` (or `python scripts/load_star_to_postgres.py`)
3. Power BI → Get data → PostgreSQL → `localhost` / database `postgres` / schema `airport_authority`
4. Wire relationships as listed in `sql/README.md`
5. Mark `dim_date` as date table
6. Paste DAX from `measures/measures.md` (map column names to snake_case if needed)
7. Build pages from `report/page-checklist.md`

### Option B: CSV files

1. Get data → Text/CSV → load every file in `data/star/`
2. Relationships:

| From | To | Column |
|------|-----|--------|
| DimDate[Date] | FactFlightOperations[Date] | 1:* |
| DimAirline[AirlineKey] | FactFlightOperations[AirlineKey] | 1:* |
| DimOriginAirport[OriginAirportKey] | FactFlightOperations[OriginAirportKey] | 1:* |
| DimDestAirport[DestAirportKey] | FactFlightOperations[DestAirportKey] | 1:* |
| DimRoute[RouteKey] | FactFlightOperations[RouteKey] | 1:* |
| DimDate[Date] | FactDelayCauseMinutes[Date] | 1:* |
| DimAirline[AirlineKey] | FactDelayCauseMinutes[AirlineKey] | 1:* |

## Headline quality snapshot (ATL, 2025 full year)

| Metric | Value |
|--------|-------|
| Fact rows | 628,872 |
| Cancellation rate | ~1.5% |
| Arrival delay rate (non-cancel, >15 min) | ~20.7% |
| OTP (non-cancel, ArrDelay <= 15) | ~79.0% |
| Airlines | 12 |
| Routes | 301 |

Details: `data/dictionary/quality-metrics.json`.

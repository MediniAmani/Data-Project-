"""Build Airport Authority star-schema tables from BTS On-Time data.

This script is the TRANSFORM step of the pipeline:

  BTS monthly zips  -->  (this file)  -->  data/star/*.csv
                                      -->  quality-metrics.json

It does NOT download source files and it does NOT load PostgreSQL.
Downloading is handled by download_bts_range.py.
Loading the warehouse is handled by load_star_to_postgres.py.

Scope (formation default):
  Home airport = ATL (Hartsfield-Jackson Atlanta International).
  Fact grain = one scheduled flight occurrence touching ATL (origin or destination)
  across the selected year of monthly BTS PREZIP files.

Feedback page: Path B (ops quality proxies). No synthetic passenger scores.

Run from airport-authority folder:
  python scripts/build_star_schema.py
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Project paths
# ROOT = airport-authority/  (one level above scripts/)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
MONTHLY_DIR = RAW_DIR / "bts_monthly"  # input: On_Time_YYYY_MM.zip
STAR_DIR = ROOT / "data" / "star"  # output: Dim*.csv / Fact*.csv
DICT_DIR = ROOT / "data" / "dictionary"  # output: quality-metrics.json

# ---------------------------------------------------------------------------
# Locked business parameters (change here if the study scope changes)
# ---------------------------------------------------------------------------
HOME_AIRPORT = "ATL"  # airport-authority perimeter
DELAY_THRESHOLD_MIN = 15  # industry-style on-time cutoff (minutes)
YEAR = 2025  # build year; all 12 monthly zips must exist

# Common BTS reporting carrier codes -> display names for DimAirline.
# Unknown codes fall back to the raw code itself later in the dim build.
AIRLINE_NAMES = {
    "9E": "Endeavor Air",
    "AA": "American Airlines",
    "AS": "Alaska Airlines",
    "B6": "JetBlue Airways",
    "DL": "Delta Air Lines",
    "F9": "Frontier Airlines",
    "G4": "Allegiant Air",
    "HA": "Hawaiian Airlines",
    "MQ": "Envoy Air",
    "NK": "Spirit Airlines",
    "OH": "PSA Airlines",
    "OO": "SkyWest Airlines",
    "QX": "Horizon Air",
    "UA": "United Airlines",
    "WN": "Southwest Airlines",
    "YV": "Mesa Airlines",
    "YX": "Republic Airways",
}


def find_monthly_zips(year: int = YEAR) -> list[Path]:
    """Return the 12 monthly BTS zip paths for ``year``, sorted.

    The build is refused if any month is missing. That keeps the year coverage
    complete and avoids silently publishing a partial dashboard.
    """
    zips = sorted(MONTHLY_DIR.glob(f"On_Time_{year}_*.zip"))
    if len(zips) != 12:
        raise SystemExit(
            f"Expected 12 monthly zips in {MONTHLY_DIR} for {year}, found {len(zips)}"
        )
    return zips


def load_bts_month(zip_path: Path, usecols: list[str]) -> pd.DataFrame:
    """Read one monthly BTS zip without extracting it to disk.

    Each PREZIP contains a long-named CSV plus a readme. We open the first CSV
    member and load only ``usecols`` to keep memory under control on a full year.
    """
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise SystemExit(f"No CSV inside {zip_path.name}")
        with zf.open(csv_names[0]) as fh:
            # low_memory=False: avoid mixed-type chunk inference on wide BTS files
            return pd.read_csv(fh, usecols=usecols, low_memory=False)


def parse_hhmm(series: pd.Series) -> pd.Series:
    """Split BTS clock integers into hour and minute components.

    BTS stores scheduled times as 1-4 digit integers, not clock strings:
      757  -> 07:57
      1455 -> 14:55

    Invalid values (NaN, hour >= 24, minute >= 60) become nullable NA so they
    do not pollute HourOfDay / TimeOfDayBank.
    """
    s = pd.to_numeric(series, errors="coerce")
    hours = (s // 100).astype("Int64")
    mins = (s % 100).astype("Int64")
    # invalid minutes / hours -> NA
    bad = (mins >= 60) | (hours >= 24) | s.isna()
    hours = hours.mask(bad)
    mins = mins.mask(bad)
    return hours, mins


def delay_bucket(arr_delay: float, cancelled: bool) -> str:
    """Map one flight's arrival delay into a severity label for slicing.

    Buckets are locked for the memoir / dashboard:
      Cancelled | Unknown | On time | 15-45 | 45-120 | 120+
    """
    if cancelled:
        return "Cancelled"
    if pd.isna(arr_delay):
        return "Unknown"
    if arr_delay <= DELAY_THRESHOLD_MIN:
        return "On time"
    if arr_delay <= 45:
        return "15-45"
    if arr_delay <= 120:
        return "45-120"
    return "120+"


def time_bank(hour) -> str:
    """Group scheduled departure hour into operational day parts.

    Night < 6, Morning < 12, Afternoon < 18, else Evening.
    Used for "which time window should ops prioritize" analysis.
    """
    if pd.isna(hour):
        return "Unknown"
    h = int(hour)
    if h < 6:
        return "Night"
    if h < 12:
        return "Morning"
    if h < 18:
        return "Afternoon"
    return "Evening"


def main() -> None:
    """Run the full year transform and write star CSVs + quality metrics."""

    # Ensure output folders exist (safe to re-run).
    STAR_DIR.mkdir(parents=True, exist_ok=True)
    DICT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1) LOAD: stack all 12 monthly national extracts
    # ------------------------------------------------------------------
    zips = find_monthly_zips(YEAR)
    print(f"reading {len(zips)} monthly zips for {YEAR} from {MONTHLY_DIR}")

    # Only columns needed for ATL ops KPIs, dims, and delay-cause charts.
    # Dropping unused BTS fields early reduces RAM on ~7M national rows.
    usecols = [
        "FlightDate",
        "Reporting_Airline",
        "IATA_CODE_Reporting_Airline",
        "Flight_Number_Reporting_Airline",
        "Tail_Number",
        "Origin",
        "OriginCityName",
        "OriginState",
        "Dest",
        "DestCityName",
        "DestState",
        "CRSDepTime",  # scheduled departure (hhmm integer)
        "DepDelayMinutes",
        "CRSArrTime",
        "ArrDelayMinutes",
        "Cancelled",
        "CancellationCode",
        "Diverted",
        # BTS cause breakdown (minutes); later unpivoted into FactDelayCauseMinutes
        "CarrierDelay",
        "WeatherDelay",
        "NASDelay",
        "SecurityDelay",
        "LateAircraftDelay",
        "Distance",
    ]

    frames = []
    for zp in zips:
        print("  ", zp.name)
        frames.append(load_bts_month(zp, usecols))
    # One national frame for the year (before ATL filter).
    df = pd.concat(frames, ignore_index=True)
    raw_rows = len(df)
    source_label = f"{YEAR}_full_year_{len(zips)}_months"

    # ------------------------------------------------------------------
    # 2) SCOPE: airport-authority lens (touch ATL as origin or destination)
    #    We are NOT modeling the full US network in Power BI.
    # ------------------------------------------------------------------
    df = df[(df["Origin"] == HOME_AIRPORT) | (df["Dest"] == HOME_AIRPORT)].copy()
    scoped_rows = len(df)

    # ------------------------------------------------------------------
    # 3) NORMALIZE: types, codes, and boolean flags
    # ------------------------------------------------------------------
    df["FlightDate"] = pd.to_datetime(df["FlightDate"])

    # Prefer IATA code when present; otherwise fall back to Reporting_Airline.
    df["CarrierCode"] = (
        df["IATA_CODE_Reporting_Airline"]
        .fillna(df["Reporting_Airline"])
        .astype(str)
        .str.strip()
        .str.upper()
    )
    df["FlightNumber"] = df["Flight_Number_Reporting_Airline"].astype(str).str.strip()
    df["Origin"] = df["Origin"].astype(str).str.strip().str.upper()
    df["Dest"] = df["Dest"].astype(str).str.strip().str.upper()

    # BTS stores Cancelled / Diverted as 0/1 (sometimes float-like). Coerce hard.
    df["IsCancelled"] = pd.to_numeric(df["Cancelled"], errors="coerce").fillna(0).astype(int) == 1
    df["IsDiverted"] = pd.to_numeric(df["Diverted"], errors="coerce").fillna(0).astype(int) == 1

    df["DepDelayMinutes"] = pd.to_numeric(df["DepDelayMinutes"], errors="coerce")
    df["ArrDelayMinutes"] = pd.to_numeric(df["ArrDelayMinutes"], errors="coerce")

    # ------------------------------------------------------------------
    # 4) CANCEL RULE (locked):
    #    - Keep cancelled rows so cancellation rate is correct.
    #    - Null delay minutes so averages / OTP are not polluted by cancels.
    # ------------------------------------------------------------------
    df.loc[df["IsCancelled"], "DepDelayMinutes"] = pd.NA
    df.loc[df["IsCancelled"], "ArrDelayMinutes"] = pd.NA

    # ------------------------------------------------------------------
    # 5) DERIVED KPI FLAGS (locked 15-minute rule)
    #    Delayed  = not cancelled AND delay minutes > 15
    #    On time  = not cancelled AND ArrDelayMinutes <= 15
    #    fillna(9999) on on-time check: missing arrival delay counts as NOT on time
    # ------------------------------------------------------------------
    df["IsDepDelayed"] = (~df["IsCancelled"]) & (df["DepDelayMinutes"] > DELAY_THRESHOLD_MIN)
    df["IsArrDelayed"] = (~df["IsCancelled"]) & (df["ArrDelayMinutes"] > DELAY_THRESHOLD_MIN)
    df["IsOnTimeArrival"] = (~df["IsCancelled"]) & (df["ArrDelayMinutes"].fillna(9999) <= DELAY_THRESHOLD_MIN)

    # Severity buckets for distribution visuals (page filters / legends).
    df["DelayBucket"] = [
        delay_bucket(a, c) for a, c in zip(df["ArrDelayMinutes"], df["IsCancelled"])
    ]

    # Time-of-day attributes from scheduled departure (CRS), not actual.
    dep_h, _ = parse_hhmm(df["CRSDepTime"])
    df["HourOfDay"] = dep_h
    df["TimeOfDayBank"] = df["HourOfDay"].map(time_bank)

    # ------------------------------------------------------------------
    # 6) KEYS
    #    RouteKey  : Origin-Dest (for DimRoute / route ranking)
    #    FlightKey : grain key for one scheduled occurrence (see quality grain text)
    #    TouchesHomeAs : whether ATL is origin, dest, or both
    # ------------------------------------------------------------------
    df["RouteKey"] = df["Origin"] + "-" + df["Dest"]
    df["FlightKey"] = (
        df["CarrierCode"]
        + "|"
        + df["FlightDate"].dt.strftime("%Y-%m-%d")
        + "|"
        + df["FlightNumber"]
        + "|"
        + df["Origin"]
        + "|"
        + df["Dest"]
    )
    df["TouchesHomeAs"] = "Other"
    df.loc[df["Origin"] == HOME_AIRPORT, "TouchesHomeAs"] = "Origin"
    df.loc[df["Dest"] == HOME_AIRPORT, "TouchesHomeAs"] = "Dest"
    df.loc[(df["Origin"] == HOME_AIRPORT) & (df["Dest"] == HOME_AIRPORT), "TouchesHomeAs"] = "Both"

    # ------------------------------------------------------------------
    # 7) DEDUPE on FlightKey (keep first). Count removals for the quality log.
    # ------------------------------------------------------------------
    before_dedupe = len(df)
    df = df.drop_duplicates(subset=["FlightKey"], keep="first")
    duplicates_removed = before_dedupe - len(df)

    # ==================================================================
    # 8) DIMENSION TABLES
    #    Star schema: facts hold measures/events; dims hold descriptive attributes.
    #    Power BI (or Postgres) will relate dims -> facts on the key columns.
    # ==================================================================

    # DimAirline: one row per carrier code seen in the ATL-scoped fact set.
    dim_airline = (
        df[["CarrierCode"]]
        .drop_duplicates()
        .assign(AirlineName=lambda x: x["CarrierCode"].map(AIRLINE_NAMES).fillna(x["CarrierCode"]))
        .rename(columns={"CarrierCode": "AirlineKey"})
        .sort_values("AirlineKey")
    )

    # Build a shared airport list from both origin and dest sides, then fork
    # into DimOriginAirport / DimDestAirport with role-specific column names.
    # Power BI often models origin and dest as two roles of the same geography.
    origin_airports = df[["Origin", "OriginCityName", "OriginState"]].drop_duplicates()
    origin_airports.columns = ["AirportKey", "CityName", "State"]
    dest_airports = df[["Dest", "DestCityName", "DestState"]].drop_duplicates()
    dest_airports.columns = ["AirportKey", "CityName", "State"]
    airports = (
        pd.concat([origin_airports, dest_airports], ignore_index=True)
        .drop_duplicates(subset=["AirportKey"])
        .sort_values("AirportKey")
    )
    dim_origin = airports.rename(
        columns={"AirportKey": "OriginAirportKey", "CityName": "OriginCity", "State": "OriginState"}
    )
    dim_dest = airports.rename(
        columns={"AirportKey": "DestAirportKey", "CityName": "DestCity", "State": "DestState"}
    )

    # DimRoute: distinct Origin-Dest pairs present in the fact set.
    dim_route = (
        df[["RouteKey", "Origin", "Dest"]]
        .drop_duplicates()
        .rename(columns={"Origin": "OriginAirportKey", "Dest": "DestAirportKey"})
        .sort_values("RouteKey")
    )

    # DimDate: continuous calendar from first to last flight date (no gaps).
    # Mark as date table in Power BI. DayOfWeek: 1=Monday ... 7=Sunday.
    min_d, max_d = df["FlightDate"].min(), df["FlightDate"].max()
    dim_date = pd.DataFrame({"Date": pd.date_range(min_d, max_d, freq="D")})
    dim_date["Year"] = dim_date["Date"].dt.year
    dim_date["Month"] = dim_date["Date"].dt.month
    dim_date["MonthName"] = dim_date["Date"].dt.strftime("%B")
    dim_date["Quarter"] = dim_date["Date"].dt.quarter
    dim_date["WeekOfYear"] = dim_date["Date"].dt.isocalendar().week.astype(int)
    dim_date["DayOfWeek"] = dim_date["Date"].dt.dayofweek + 1  # 1=Mon
    dim_date["DayOfWeekName"] = dim_date["Date"].dt.day_name()
    dim_date["IsWeekend"] = dim_date["DayOfWeek"].isin([6, 7])

    # ==================================================================
    # 9) FACT TABLES
    # ==================================================================

    # FactFlightOperations: one row per ATL-touching scheduled occurrence.
    # Column renames align CSV headers with Power BI / Postgres key names.
    fact = df[
        [
            "FlightKey",
            "FlightDate",
            "CarrierCode",
            "FlightNumber",
            "Tail_Number",
            "Origin",
            "Dest",
            "RouteKey",
            "HourOfDay",
            "TimeOfDayBank",
            "TouchesHomeAs",
            "IsCancelled",
            "CancellationCode",
            "IsDiverted",
            "DepDelayMinutes",
            "ArrDelayMinutes",
            "IsDepDelayed",
            "IsArrDelayed",
            "IsOnTimeArrival",
            "DelayBucket",
            "Distance",
            "CarrierDelay",
            "WeatherDelay",
            "NASDelay",
            "SecurityDelay",
            "LateAircraftDelay",
        ]
    ].rename(
        columns={
            "FlightDate": "Date",
            "CarrierCode": "AirlineKey",
            "Origin": "OriginAirportKey",
            "Dest": "DestAirportKey",
            "Tail_Number": "TailNumber",
        }
    )

    # FactDelayCauseMinutes: unpivot wide BTS cause columns into long form.
    # One cause-minute row only when minutes > 0 (keeps the table lean for charts).
    cause_cols = {
        "CarrierDelay": "Carrier",
        "WeatherDelay": "Weather",
        "NASDelay": "NAS",
        "SecurityDelay": "Security",
        "LateAircraftDelay": "LateAircraft",
    }
    cause_frames = []
    for col, label in cause_cols.items():
        tmp = fact[["FlightKey", "Date", "AirlineKey", col]].copy()
        tmp["CauseType"] = label
        tmp["DelayCauseMinutes"] = pd.to_numeric(tmp[col], errors="coerce")
        tmp = tmp.dropna(subset=["DelayCauseMinutes"])
        tmp = tmp[tmp["DelayCauseMinutes"] > 0]
        cause_frames.append(
            tmp[["FlightKey", "Date", "AirlineKey", "CauseType", "DelayCauseMinutes"]]
        )
    fact_causes = pd.concat(cause_frames, ignore_index=True) if cause_frames else pd.DataFrame()

    # ------------------------------------------------------------------
    # 10) WRITE intermediate star CSVs (auditable checkpoint before Postgres)
    # ------------------------------------------------------------------
    dim_airline.to_csv(STAR_DIR / "DimAirline.csv", index=False)
    dim_origin.to_csv(STAR_DIR / "DimOriginAirport.csv", index=False)
    dim_dest.to_csv(STAR_DIR / "DimDestAirport.csv", index=False)
    dim_route.to_csv(STAR_DIR / "DimRoute.csv", index=False)
    dim_date.to_csv(STAR_DIR / "DimDate.csv", index=False)
    fact.to_csv(STAR_DIR / "FactFlightOperations.csv", index=False)
    fact_causes.to_csv(STAR_DIR / "FactDelayCauseMinutes.csv", index=False)

    # ------------------------------------------------------------------
    # 11) QUALITY SNAPSHOT for the memoir / method documentation
    #     Re-run this script whenever source months change; refresh the JSON.
    # ------------------------------------------------------------------
    non_cancel = fact[~fact["IsCancelled"]]
    quality = {
        "source_file": source_label,
        "home_airport": HOME_AIRPORT,
        "delay_threshold_minutes": DELAY_THRESHOLD_MIN,
        "feedback_path": "B_ops_proxies",
        "grain": (
            "One row in FactFlightOperations = one scheduled flight occurrence "
            "(carrier + flight date + flight number + origin + destination) touching ATL, after dedupe."
        ),
        "raw_rows_year_files": raw_rows,
        "rows_after_home_scope": scoped_rows,
        "duplicates_removed": int(duplicates_removed),
        "fact_rows": int(len(fact)),
        "date_min": str(min_d.date()),
        "date_max": str(max_d.date()),
        "null_rate_arr_delay_non_cancel": float(non_cancel["ArrDelayMinutes"].isna().mean()),
        "cancellation_rate": float(fact["IsCancelled"].mean()),
        "arrival_delay_rate_non_cancel": float(non_cancel["IsArrDelayed"].mean()),
        "otp_non_cancel": float(non_cancel["IsOnTimeArrival"].mean()),
        "airlines": int(dim_airline.shape[0]),
        "routes": int(dim_route.shape[0]),
        "cause_rows": int(len(fact_causes)),
    }
    (DICT_DIR / "quality-metrics.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    print(json.dumps(quality, indent=2))
    print("wrote star tables to", STAR_DIR)


if __name__ == "__main__":
    # Standard entry point: `python scripts/build_star_schema.py`
    main()

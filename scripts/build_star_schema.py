"""Build Airport Authority star-schema tables from BTS On-Time data.

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

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
MONTHLY_DIR = RAW_DIR / "bts_monthly"
STAR_DIR = ROOT / "data" / "star"
DICT_DIR = ROOT / "data" / "dictionary"

HOME_AIRPORT = "ATL"
DELAY_THRESHOLD_MIN = 15
YEAR = 2025

# Common BTS reporting carrier codes -> display names (extend as needed)
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
    zips = sorted(MONTHLY_DIR.glob(f"On_Time_{year}_*.zip"))
    if len(zips) != 12:
        raise SystemExit(
            f"Expected 12 monthly zips in {MONTHLY_DIR} for {year}, found {len(zips)}"
        )
    return zips


def load_bts_month(zip_path: Path, usecols: list[str]) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise SystemExit(f"No CSV inside {zip_path.name}")
        with zf.open(csv_names[0]) as fh:
            return pd.read_csv(fh, usecols=usecols, low_memory=False)


def parse_hhmm(series: pd.Series) -> pd.Series:
    """BTS times are often 1-4 digit integers like 757 or 1455."""
    s = pd.to_numeric(series, errors="coerce")
    hours = (s // 100).astype("Int64")
    mins = (s % 100).astype("Int64")
    # invalid minutes -> NA
    bad = (mins >= 60) | (hours >= 24) | s.isna()
    hours = hours.mask(bad)
    mins = mins.mask(bad)
    return hours, mins


def delay_bucket(arr_delay: float, cancelled: bool) -> str:
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
    STAR_DIR.mkdir(parents=True, exist_ok=True)
    DICT_DIR.mkdir(parents=True, exist_ok=True)

    zips = find_monthly_zips(YEAR)
    print(f"reading {len(zips)} monthly zips for {YEAR} from {MONTHLY_DIR}")

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
        "CRSDepTime",
        "DepDelayMinutes",
        "CRSArrTime",
        "ArrDelayMinutes",
        "Cancelled",
        "CancellationCode",
        "Diverted",
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
    df = pd.concat(frames, ignore_index=True)
    raw_rows = len(df)
    source_label = f"{YEAR}_full_year_{len(zips)}_months"

    # Home airport authority scope
    df = df[(df["Origin"] == HOME_AIRPORT) | (df["Dest"] == HOME_AIRPORT)].copy()
    scoped_rows = len(df)

    df["FlightDate"] = pd.to_datetime(df["FlightDate"])
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

    df["IsCancelled"] = pd.to_numeric(df["Cancelled"], errors="coerce").fillna(0).astype(int) == 1
    df["IsDiverted"] = pd.to_numeric(df["Diverted"], errors="coerce").fillna(0).astype(int) == 1

    df["DepDelayMinutes"] = pd.to_numeric(df["DepDelayMinutes"], errors="coerce")
    df["ArrDelayMinutes"] = pd.to_numeric(df["ArrDelayMinutes"], errors="coerce")

    # Cancelled: keep cancel rate, null out delay minutes for averages
    df.loc[df["IsCancelled"], "DepDelayMinutes"] = pd.NA
    df.loc[df["IsCancelled"], "ArrDelayMinutes"] = pd.NA

    df["IsDepDelayed"] = (~df["IsCancelled"]) & (df["DepDelayMinutes"] > DELAY_THRESHOLD_MIN)
    df["IsArrDelayed"] = (~df["IsCancelled"]) & (df["ArrDelayMinutes"] > DELAY_THRESHOLD_MIN)
    df["IsOnTimeArrival"] = (~df["IsCancelled"]) & (df["ArrDelayMinutes"].fillna(9999) <= DELAY_THRESHOLD_MIN)

    df["DelayBucket"] = [
        delay_bucket(a, c) for a, c in zip(df["ArrDelayMinutes"], df["IsCancelled"])
    ]

    dep_h, _ = parse_hhmm(df["CRSDepTime"])
    df["HourOfDay"] = dep_h
    df["TimeOfDayBank"] = df["HourOfDay"].map(time_bank)

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

    before_dedupe = len(df)
    df = df.drop_duplicates(subset=["FlightKey"], keep="first")
    duplicates_removed = before_dedupe - len(df)

    # --- dims ---
    dim_airline = (
        df[["CarrierCode"]]
        .drop_duplicates()
        .assign(AirlineName=lambda x: x["CarrierCode"].map(AIRLINE_NAMES).fillna(x["CarrierCode"]))
        .rename(columns={"CarrierCode": "AirlineKey"})
        .sort_values("AirlineKey")
    )

    origin_airports = df[["Origin", "OriginCityName", "OriginState"]].drop_duplicates()
    origin_airports.columns = ["AirportKey", "CityName", "State"]
    dest_airports = df[["Dest", "DestCityName", "DestState"]].drop_duplicates()
    dest_airports.columns = ["AirportKey", "CityName", "State"]
    airports = (
        pd.concat([origin_airports, dest_airports], ignore_index=True)
        .drop_duplicates(subset=["AirportKey"])
        .sort_values("AirportKey")
    )
    dim_origin = airports.rename(columns={"AirportKey": "OriginAirportKey", "CityName": "OriginCity", "State": "OriginState"})
    dim_dest = airports.rename(columns={"AirportKey": "DestAirportKey", "CityName": "DestCity", "State": "DestState"})

    dim_route = (
        df[["RouteKey", "Origin", "Dest"]]
        .drop_duplicates()
        .rename(columns={"Origin": "OriginAirportKey", "Dest": "DestAirportKey"})
        .sort_values("RouteKey")
    )

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

    # Unpivoted delay causes for optional FactDelayCauseMinutes
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
        cause_frames.append(tmp[["FlightKey", "Date", "AirlineKey", "CauseType", "DelayCauseMinutes"]])
    fact_causes = pd.concat(cause_frames, ignore_index=True) if cause_frames else pd.DataFrame()

    # Write stars
    dim_airline.to_csv(STAR_DIR / "DimAirline.csv", index=False)
    dim_origin.to_csv(STAR_DIR / "DimOriginAirport.csv", index=False)
    dim_dest.to_csv(STAR_DIR / "DimDestAirport.csv", index=False)
    dim_route.to_csv(STAR_DIR / "DimRoute.csv", index=False)
    dim_date.to_csv(STAR_DIR / "DimDate.csv", index=False)
    fact.to_csv(STAR_DIR / "FactFlightOperations.csv", index=False)
    fact_causes.to_csv(STAR_DIR / "FactDelayCauseMinutes.csv", index=False)

    # Quality metrics
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
    main()

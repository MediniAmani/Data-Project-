"""Download BTS On-Time Reporting Carrier monthly zips for a year range.

Default: 2009-01 through 2018-12 (120 files).
Skips files that already exist and look complete (>1 MB).

Usage (from airport-authority folder):
  python scripts/download_bts_range.py
  python scripts/download_bts_range.py --start 2009 --end 2018
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "bts_monthly"

URL_TMPL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)


def download_one(year: int, month: int, force: bool = False) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"On_Time_{year}_{month:02d}.zip"
    url = URL_TMPL.format(year=year, month=month)

    if dest.exists() and dest.stat().st_size > 1_000_000 and not force:
        return f"SKIP {dest.name} ({dest.stat().st_size:,} bytes)"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; airport-authority-capstone/1.0)"},
    )
    tmp = dest.with_suffix(".partial")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, tmp.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
        size = tmp.stat().st_size
        if size < 1_000_000:
            tmp.unlink(missing_ok=True)
            return f"FAIL {dest.name} too small ({size} bytes) url={url}"
        tmp.replace(dest)
        return f"OK   {dest.name} ({size:,} bytes)"
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        return f"FAIL {dest.name} HTTP {e.code}"
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return f"FAIL {dest.name} {type(e).__name__}: {e}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2009)
    parser.add_argument("--end", type=int, default=2018)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.5, help="Seconds between downloads")
    args = parser.parse_args()

    if args.start > args.end:
        raise SystemExit("start year must be <= end year")

    jobs = [(y, m) for y in range(args.start, args.end + 1) for m in range(1, 13)]
    print(f"Downloading {len(jobs)} monthly zips into {OUT_DIR}", flush=True)

    ok = skip = fail = 0
    for i, (year, month) in enumerate(jobs, start=1):
        msg = download_one(year, month, force=args.force)
        print(f"[{i}/{len(jobs)}] {msg}", flush=True)
        if msg.startswith("OK"):
            ok += 1
        elif msg.startswith("SKIP"):
            skip += 1
        else:
            fail += 1
        time.sleep(args.sleep)

    print(f"Done. ok={ok} skip={skip} fail={fail}", flush=True)
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

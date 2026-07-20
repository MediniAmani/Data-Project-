# Quality log

Generated from `scripts/build_star_schema.py` on the January 2023 BTS file, ATL scope.

## Grain (frozen)

One row in `FactFlightOperations` = one scheduled flight occurrence (carrier + flight date + flight number + origin + destination) touching ATL, after dedupe.

## Checks

| Check | Result |
|-------|--------|
| Raw rows in month file | 538,837 |
| Rows after ATL origin/dest filter | 53,148 |
| Duplicates removed on FlightKey | 0 |
| Fact rows loaded | 53,148 |
| Date coverage | 2023-01-01 to 2023-01-31 |
| Null ArrDelayMinutes among non-cancelled | 0.28% |
| Cancellation rate | 0.91% |
| Arrival delay rate (>15 min, non-cancel) | 20.1% |
| OTP (ArrDelay <= 15, non-cancel) | 79.7% |
| Distinct airlines | 13 |
| Distinct routes | 294 |
| Delay cause minute rows (>0) | 17,015 |

## Rules locked

1. Cancelled flights: counted in cancellation rate; delay minutes set to null so averages exclude them.
2. Delayed = delay minutes > 15.
3. On-time arrival = not cancelled and ArrDelayMinutes <= 15.
4. Delay buckets: On time / 15-45 / 45-120 / 120+ / Cancelled / Unknown.
5. Time banks from CRSDepTime hour: Night <6, Morning <12, Afternoon <18, Evening otherwise.

## Open risks for memoir

- Single month only: MoM/YTD need more months if the jury asks for longer trends.
- ATL is a Delta hub: airline mix is not nationally balanced; say so.
- Path B feedback: no passenger survey join in this build.

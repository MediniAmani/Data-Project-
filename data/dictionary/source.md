# Source

- **Dataset:** Airline On-Time Performance Data (Reporting Carrier), US Bureau of Transportation Statistics (BTS)
- **File used:** `On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2023_1.csv` (January 2023)
- **Download pattern:** `https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_YYYY_M.zip`
- **Official portal:** https://transtats.bts.gov/
- **Access date:** 2026-07-17
- **License / use:** US government public statistical data. Credit BTS / OST-R in the memoir and report footer.

## Formation scope applied on top of source

- Home airport: ATL
- Keep rows where Origin = ATL or Dest = ATL
- Delay threshold: 15 minutes (document in jury defense; optional what-if later)

## Feedback

Path B: passenger feedback is not in this BTS extract. Use ops proxies (OTP, cancellation rate, severe delay share, Ops Stress Index) on the feedback/quality page. Do not invent survey scores.

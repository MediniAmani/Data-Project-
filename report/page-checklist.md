# Report page checklist

Build in Power BI Desktop after relationships and measures are in place.

Slicers on every page (where useful): Date, AirlineName, OriginAirportKey, DestAirportKey, TouchesHomeAs, TimeOfDayBank, DelayBucket.

## Page 1: Executive Summary

- [ ] Cards: Total Flights, On Time Performance, Cancellation Rate, Avg Arrival Delay Min, Ops Stress Index
- [ ] Line: daily OTP or Avg Arrival Delay Min
- [ ] Bar: top 5 airlines by Total Arrival Delay Min
- [ ] Title states ATL authority scope + Jan 2023

## Page 2: Flight Ops Pulse

- [ ] Stacked column: flights by Date and DelayBucket
- [ ] Matrix: DayOfWeekName × HourOfDay with Arrival Delay Rate
- [ ] Treemap: RouteKey by Total Flights
- [ ] Card: diverted count (`IsDiverted`)

## Page 3: Delay Deep Dive

- [ ] DelayBucket distribution
- [ ] Stacked bar / ribbon: Total Cause Delay Min by CauseType
- [ ] Ranked bar: causes by minutes
- [ ] Table: top routes by Total Arrival Delay Min

## Page 4: Route and Airline Rankings

- [ ] Scatter: Operated volume vs Arrival Delay Rate by airline (size = Total Arrival Delay Min)
- [ ] Top routes by Total Arrival Delay Min
- [ ] Clustered bar: Cancellation Rate by airline
- [ ] Volume floor note on page (exclude tiny airlines from “worst” claims)

## Page 5: Ops Quality Proxies (Path B)

- [ ] Ops Stress Index by airline
- [ ] Severe Delay Share vs Arrival Delay Rate
- [ ] Caption: passenger surveys not in BTS extract; proxies used until a feedback join exists

## Page 6: Decision Storyboard

- [ ] Protect: top 3 routes by Total Arrival Delay Min
- [ ] Challenge: top 3 material-volume airlines by Arrival Delay Rate
- [ ] Watch: worst TimeOfDayBank × DayOfWeek cells from the matrix
- [ ] Next check: what to re-measure after one week
- [ ] Bookmark pair: Incident day vs Normal week (optional polish)

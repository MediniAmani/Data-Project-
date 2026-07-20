# Measure dictionary

Create a blank table named `Measures` in Power BI, then add these measures.

Delay threshold in the star extract: **15 minutes**.

## Volume and status

```dax
Total Flights = COUNTROWS( FactFlightOperations )

Cancelled Flights =
CALCULATE(
    [Total Flights],
    FactFlightOperations[IsCancelled] = TRUE()
)

Cancellation Rate =
DIVIDE( [Cancelled Flights], [Total Flights] )

On Time Arrivals =
CALCULATE(
    [Total Flights],
    FactFlightOperations[IsOnTimeArrival] = TRUE()
)

Operated Flights =
[Total Flights] - [Cancelled Flights]

On Time Performance =
DIVIDE( [On Time Arrivals], [Operated Flights] )
```

## Delay severity

```dax
Avg Arrival Delay Min =
AVERAGEX(
    FILTER( FactFlightOperations, NOT FactFlightOperations[IsCancelled] ),
    FactFlightOperations[ArrDelayMinutes]
)

Total Arrival Delay Min =
SUMX(
    FILTER( FactFlightOperations, NOT FactFlightOperations[IsCancelled] ),
    FactFlightOperations[ArrDelayMinutes]
)

Delayed Arrival Flights =
CALCULATE(
    [Total Flights],
    FactFlightOperations[IsArrDelayed] = TRUE()
)

Arrival Delay Rate =
DIVIDE( [Delayed Arrival Flights], [Operated Flights] )

Severe Delay Flights =
CALCULATE(
    [Total Flights],
    FactFlightOperations[DelayBucket] = "120+"
)

Severe Delay Share =
DIVIDE( [Severe Delay Flights], [Operated Flights] )
```

## Ops quality proxies (feedback Path B)

```dax
Ops Stress Index =
[Arrival Delay Rate] * 0.5
    + [Cancellation Rate] * 0.3
    + [Severe Delay Share] * 0.2
```

## Cause minutes (use FactDelayCauseMinutes)

```dax
Total Cause Delay Min =
SUM( FactDelayCauseMinutes[DelayCauseMinutes] )
```

## Ranking helpers

```dax
Airline Delay Rank =
RANKX(
    ALL( DimAirline[AirlineName] ),
    [Total Arrival Delay Min],
    ,
    DESC,
    DENSE
)

Route Delay Rank =
RANKX(
    ALL( DimRoute[RouteKey] ),
    [Total Arrival Delay Min],
    ,
    DESC,
    DENSE
)
```

## Notes for jury

- OTP denominator = operated flights (excludes cancelled).
- For airline rankings on delay rate, filter or annotate carriers with very low volume to avoid false “worst airline” stories.
- Add a disconnected what-if table later if you want threshold sensitivity (15 / 30 / 45).

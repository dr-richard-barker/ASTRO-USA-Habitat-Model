# S3 HVAC off, door closed: CO₂ build-up (ledger bf8f08efaf8171a1)

Well-mixed 63.1 m³ of air (CFD fluid volume), crew at BVAD's awake 0.69 g CO₂/min each, starting from outdoor air (426.1 ppm, NOAA). Limit: OSHA PEL 5000 ppm, an 8-hour time-weighted average, so reaching it is a warning level, not an instant hazard. Plants (CO₂ uptake not modelled) and temperature (thermal mass unknown) are left out.

| crew | infiltration (ACH) | initial rise (ppm/h) | hours to 5000 ppm | steady level (ppm) |
|---|---|---|---|---|
| 2 | 0 | 727 | 6.29 | keeps rising |
| 2 | 0.1 | 727 | 9.92 | 7694.0 |
| 2 | 0.5 | 727 | never | 1880.0 |
| 6 | 0 | 2180 | 2.1 | keeps rising |
| 6 | 0.1 | 2180 | 2.35 | 22230.0 |
| 6 | 0.5 | 2180 | never | 4787.0 |

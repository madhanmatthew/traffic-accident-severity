# Model monitoring report - 2026-10-07T05:38:58+00:00

Rows analysed: **26,342**

## Decision: no retraining needed

- no retraining criteria met

**Warnings**
- feature drift on ['temperature_c']
- input data-quality alarm - missing-rate increase on ['special_conditions_at_site'] (fix upstream before retraining)

## Class drift

```json
{
  "prediction_distribution": {
    "Fatal": 0.04741477488421532,
    "Serious": 0.37457292536633513,
    "Slight": 0.5780122997494496
  },
  "reference_prediction_distribution": {
    "Fatal": 0.04748742754040462,
    "Serious": 0.3754846635187531,
    "Slight": 0.5770279089408422
  },
  "prediction_psi": 0.0,
  "actual_distribution": {
    "Fatal": 0.014843216156707919,
    "Serious": 0.22386303241970998,
    "Slight": 0.7612937514235821
  },
  "reference_actual_distribution": {
    "Fatal": 0.014590793671462985,
    "Serious": 0.22702649912103653,
    "Slight": 0.7583827072075005
  },
  "actual_psi": 0.0001
}
```

## Location drift

```json
{
  "police_force": 0.0118,
  "nation": 0.0007,
  "centroid_shift_km": 1.67
}
```

## Feature drift (top 15 by PSI)

| feature | PSI | status |
|---|---|---|
| month | 6.558 | significant |
| temperature_c | 0.747 | significant |
| special_conditions_at_site | 0.6716 | significant |
| humidity_pct | 0.4614 | significant |
| light_conditions | 0.1316 | moderate |
| wind_gusts_kmh | 0.0744 | stable |
| road_surface_conditions | 0.0548 | stable |
| cloud_cover_pct | 0.043 | stable |
| wind_speed_kmh | 0.0428 | stable |
| weather_conditions | 0.0306 | stable |
| junction_detail | 0.0304 | stable |
| precipitation_mm | 0.0232 | stable |
| carriageway_hazards | 0.022 | stable |
| police_force | 0.0118 | stable |
| longitude | 0.0044 | stable |

## Performance (labelled batch)

- macro-F1: 0.4308 (baseline 0.43141)
- KSI false-negative rate: 0.3554 (baseline 0.35417)
- recall Fatal / Serious / Slight: 0.297 / 0.554 / 0.648

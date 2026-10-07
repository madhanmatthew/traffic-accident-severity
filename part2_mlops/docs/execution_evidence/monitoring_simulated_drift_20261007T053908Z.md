# Model monitoring report - 2026-10-07T05:39:08+00:00

Rows analysed: **9,361**

## Decision: RETRAIN

- 7 key features drifted (PSI > 0.2): ['hour', 'temperature_c', 'precipitation_mm', 'light_conditions', 'urban_or_rural', 'road_surface_conditions', 'speed_limit']
- location drift (police force PSI=0.817 > 0.2)

**Warnings**
- input data-quality alarm - missing-rate increase on ['junction_control', 'special_conditions_at_site'] (fix upstream before retraining)

## Class drift

```json
{
  "prediction_distribution": {
    "Fatal": 0.13235765409678454,
    "Serious": 0.4868069650678346,
    "Slight": 0.3808353808353808
  },
  "reference_prediction_distribution": {
    "Fatal": 0.04748742754040462,
    "Serious": 0.3754846635187531,
    "Slight": 0.5770279089408422
  },
  "prediction_psi": 0.1974,
  "actual_distribution": {
    "Fatal": 0.025638286507851726,
    "Serious": 0.26065591282982586,
    "Slight": 0.7137058006623224
  },
  "reference_actual_distribution": {
    "Fatal": 0.014590793671462985,
    "Serious": 0.22702649912103653,
    "Slight": 0.7583827072075005
  },
  "actual_psi": 0.0136
}
```

## Location drift

```json
{
  "police_force": 0.817,
  "nation": 0.1198,
  "centroid_shift_km": 43.67
}
```

## Feature drift (top 15 by PSI)

| feature | PSI | status |
|---|---|---|
| hour | 7.0208 | significant |
| month | 6.5562 | significant |
| temperature_c | 5.1778 | significant |
| precipitation_mm | 4.3622 | significant |
| light_conditions | 1.7821 | significant |
| urban_or_rural | 1.6912 | significant |
| road_surface_conditions | 1.5818 | significant |
| special_conditions_at_site | 1.0576 | significant |
| police_force | 0.817 | significant |
| speed_limit | 0.635 | significant |
| humidity_pct | 0.4731 | significant |
| longitude | 0.3059 | significant |
| latitude | 0.2638 | significant |
| junction_control | 0.1285 | moderate |
| nation | 0.1198 | moderate |

## Performance (labelled batch)

- macro-F1: 0.3862 (baseline 0.43141)
- KSI false-negative rate: 0.1929 (baseline 0.35417)
- recall Fatal / Serious / Slight: 0.367 / 0.638 / 0.456

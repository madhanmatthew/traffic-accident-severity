# Dataset sources and access instructions

All sources are free, public and contain no personally identifiable information.

| Source | What is used | Licence | Access |
|---|---|---|---|
| **UK Department for Transport - Road Safety Open Data (STATS19)** | Collision, vehicle and casualty tables for 2023 and 2024 (≈205k collisions, ≈373k vehicles, ≈261k casualties) | Open Government Licence v3.0 | Landing page: https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-safety-data · Direct files: `https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-{collision\|vehicle\|casualty}-{YEAR}.csv` |
| **Open-Meteo Historical Weather API** (ERA5-based archive) | Hourly temperature, precipitation, rain, snowfall, wind speed and gusts, cloud cover, humidity and WMO weather code | CC BY 4.0, free for non-commercial use, no API key | `https://archive-api.open-meteo.com/v1/archive?latitude=..&longitude=..&start_date=..&end_date=..&hourly=..&timezone=Europe/London` · docs: https://open-meteo.com/en/docs/historical-weather-api |
| OpenStreetMap (optional) | Not used in this version. Road type and class already come from STATS19. | ODbL | listed as a future enrichment |

## How the pipeline accesses the data

1. `extract_stats19` builds each file URL from `STATS19_BASE_URL` and `STATS19_YEARS`, then streams the file into `data/raw/stats19/<run_id>/`. It records the HTTP status, row count, size and SHA-256 in `data/logs/ingestion_log.csv`. If an earlier run already downloaded the same annual file, that copy is reused and logged as `CACHED`. DfT republishes annual files rarely; set `FORCE_DOWNLOAD=true` to download them again.
2. `extract_weather` snaps every collision to a grid cell (`WEATHER_GRID_DEG`, default 1.0°, which gives 59 cells) and requests one full year of hourly data per cell, 10 cells per call. Requests are timed to stay under the free tier's limit of 600 weighted calls per minute. One cell for one year weighs about 26 calls, so a full 2-year refresh uses about 3,000 of the 10,000 daily allowance. HTTP 429 and 5xx responses are retried with back-off. A request that still fails is logged as `FAILED` and the run continues. The affected collisions then keep `weather_matched = false`, and police-recorded weather is still available for them.
3. Times are requested in `Europe/London` local time, which matches the STATS19 `time` field.

## Reproducing the extraction manually

```bash
curl -O https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-2024.csv
curl "https://archive-api.open-meteo.com/v1/archive?latitude=51.5&longitude=-0.1&start_date=2024-01-01&end_date=2024-01-02&hourly=temperature_2m,precipitation&timezone=Europe%2FLondon"
```

## Known limitations

* Since the 2024 release, STATS19 uses `collision_*` column names; older files use `accident_*`. Staging handles both through `COLUMN_ALIASES`.
* The link to the DfT data guide (`...data-guide-2024.xlsx`) returned 404 when this was built, so code labels are kept in `src/traffic_pipeline/lookups.py`. A code that isn't in the lookup becomes `Unknown (code N)` and never breaks the pipeline.
* Weather resolution is about 1° (roughly 70 × 110 km), so it describes regional conditions, not the exact street. You can use a finer grid (`WEATHER_GRID_DEG=0.5`), but it needs about 3× more API quota.
* STATS19 only covers personal-injury collisions that were reported to the police. Damage-only collisions aren't included.

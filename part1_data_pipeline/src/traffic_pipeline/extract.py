"""Extraction (ingestion) layer.

* STATS19 collision / vehicle / casualty CSVs are downloaded from the DfT open
  data server into `data/raw/stats19/<run_id>/` unchanged (immutable raw copy).
* Hourly weather is pulled from the Open-Meteo archive API for every weather
  grid cell that contains at least one collision, and the JSON responses are
  stored unchanged in `data/raw/weather/<run_id>/`.

Every file/API call is recorded in the ingestion log with its status, row
count, size and checksum. Files that already exist from an earlier run are
re-used (status CACHED) unless FORCE_DOWNLOAD=true, which keeps scheduled
refreshes cheap and makes reruns repeatable.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from .audit import get_logger, log_ingestion, pipeline_step
from .config import WEATHER_VARIABLES, get_settings

STATS19_DATASETS = ("collision", "vehicle", "casualty")
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

logger = get_logger()


# --------------------------------------------------------------------------- helpers
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_csv_rows(path: Path) -> int:
    with path.open("rb") as fh:
        return max(sum(1 for _ in fh) - 1, 0)


def _find_cached(source_dir: Path, filename: str, current_run: Path) -> Path | None:
    candidates = sorted(
        (p for p in source_dir.glob(f"*/{filename}") if p.parent != current_run),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def http_get(url: str, *, params: dict | None = None, stream: bool = False) -> requests.Response:
    """GET with exponential back-off on rate limits and transient server errors."""
    settings = get_settings()
    last_error: Exception | None = None
    for attempt in range(1, settings.http_retries + 1):
        try:
            response = requests.get(url, params=params, stream=stream, timeout=settings.http_timeout_s)
            if response.status_code in RETRYABLE_STATUS:
                # Open-Meteo rate limits are per minute/hour, so wait at least a minute on 429.
                default_wait = 65 * attempt if response.status_code == 429 else min(15 * 2 ** (attempt - 1), 120)
                wait = int(response.headers.get("Retry-After", 0)) or default_wait
                logger.warning("HTTP %s from %s (attempt %d) - retrying in %ss",
                               response.status_code, url, attempt, wait)
                last_error = requests.HTTPError(f"HTTP {response.status_code}: {response.text[:200]}")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
            wait = min(10 * 2 ** (attempt - 1), 120)
            logger.warning("Network error on %s (attempt %d): %s - retrying in %ss", url, attempt, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"GET {url} failed after {settings.http_retries} attempts: {last_error}")


# --------------------------------------------------------------------------- STATS19
def stats19_filename(dataset: str, year: int) -> str:
    return f"dft-road-casualty-statistics-{dataset}-{year}.csv"


@pipeline_step("extract_stats19")
def extract_stats19(run_id: str) -> dict:
    settings = get_settings()
    source_dir = settings.raw_dir / "stats19"
    run_dir = source_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    total_rows, files = 0, 0
    for year in settings.stats19_years:
        for dataset in STATS19_DATASETS:
            filename = stats19_filename(dataset, year)
            url = f"{settings.stats19_base_url}/{filename}"
            target = run_dir / filename
            status, http_status, message = "SUCCESS", "", ""

            cached = None if settings.force_download else _find_cached(source_dir, filename, run_dir)
            try:
                if cached is not None:
                    shutil.copy2(cached, target)
                    status, message = "CACHED", f"re-used {cached.parent.name}/{filename}"
                else:
                    response = http_get(url, stream=True)
                    http_status = response.status_code
                    tmp = target.with_suffix(".part")
                    with tmp.open("wb") as fh:
                        for chunk in response.iter_content(chunk_size=1 << 20):
                            fh.write(chunk)
                    tmp.replace(target)
            except Exception as exc:
                log_ingestion(run_id=run_id, source="DfT STATS19", dataset=f"{dataset}_{year}", url=url,
                              status="FAILED", http_status=http_status, message=str(exc)[:500])
                # Collision files are mandatory; the run cannot continue without them.
                raise

            rows = _count_csv_rows(target)
            total_rows += rows
            files += 1
            log_ingestion(run_id=run_id, source="DfT STATS19", dataset=f"{dataset}_{year}", url=url,
                          status=status, http_status=http_status, row_count=rows,
                          bytes=target.stat().st_size, sha256=_sha256(target),
                          local_path=str(target.relative_to(settings.data_dir)), message=message)
            logger.info("%s %s: %d rows (%s)", dataset, year, rows, status)

    return {"rows_out": total_rows, "message": f"{files} STATS19 files extracted"}


# --------------------------------------------------------------------------- weather
def cell_id(lat: float, lon: float) -> str:
    return f"{lat + 0.0:.2f}_{lon + 0.0:.2f}"  # + 0.0 turns -0.0 into 0.0


def open_meteo_weight(n_locations: int, n_days: int, n_variables: int) -> float:
    """Approximate Open-Meteo API-call weight (free tier: 600/min, 5,000/h, 10,000/day).

    One call = 1 location, <= 14 days, <= 10 variables; larger requests count as
    proportionally more calls.
    """
    return n_locations * max(1.0, n_days / 14) * max(1.0, n_variables / 10)


def assign_weather_cell(df: pd.DataFrame, grid_deg: float) -> pd.DataFrame:
    """Snap each collision to the centre of a regular lat/lon grid cell."""
    df = df.copy()
    df["weather_cell_lat"] = (df["latitude"] / grid_deg).round() * grid_deg
    df["weather_cell_lon"] = (df["longitude"] / grid_deg).round() * grid_deg
    df["weather_cell_id"] = [cell_id(a, b) for a, b in zip(df["weather_cell_lat"], df["weather_cell_lon"])]
    return df


@pipeline_step("extract_weather")
def extract_weather(run_id: str) -> dict:
    """Fetch hourly weather for every (grid cell, year) that has collisions."""
    settings = get_settings()
    if not settings.weather_enabled:
        log_ingestion(run_id=run_id, source="Open-Meteo", dataset="hourly_weather", status="SKIPPED",
                      message="WEATHER_ENABLED=false")
        return {"rows_out": 0, "message": "weather extraction disabled"}

    staged = pd.read_parquet(settings.staging_dir / run_id / "collisions.parquet",
                             columns=["latitude", "longitude", "collision_date"])
    staged = staged.dropna(subset=["latitude", "longitude", "collision_date"])
    lat_ok = staged["latitude"].between(settings.uk_lat_min, settings.uk_lat_max)
    lon_ok = staged["longitude"].between(settings.uk_lon_min, settings.uk_lon_max)
    staged = assign_weather_cell(staged[lat_ok & lon_ok], settings.weather_grid_deg)
    staged["year"] = pd.to_datetime(staged["collision_date"]).dt.year

    source_dir = settings.raw_dir / "weather"
    run_dir = source_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_available = date.today() - timedelta(days=7)  # archive API lags ~5 days

    fetched, cached, failed = 0, 0, 0
    for year, group in staged.groupby("year"):
        cells = group[["weather_cell_id", "weather_cell_lat", "weather_cell_lon"]].drop_duplicates()
        start = date(int(year), 1, 1)
        end = min(date(int(year), 12, 31), latest_available)
        to_fetch = []
        for row in cells.itertuples(index=False):
            filename = f"cell_{row.weather_cell_id}_{year}.json"
            previous = None if settings.force_download else _find_cached(source_dir, filename, run_dir)
            if previous is not None:
                shutil.copy2(previous, run_dir / filename)
                cached += 1
            else:
                to_fetch.append(row)
        logger.info("Weather %s: %d cells (%d cached, %d to fetch)", year, len(cells), len(cells) - len(to_fetch),
                    len(to_fetch))

        step = settings.weather_locations_per_request
        for i in range(0, len(to_fetch), step):
            chunk = to_fetch[i:i + step]
            params = {
                "latitude": ",".join(f"{c.weather_cell_lat:.2f}" for c in chunk),
                "longitude": ",".join(f"{c.weather_cell_lon:.2f}" for c in chunk),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "hourly": ",".join(WEATHER_VARIABLES),
                "timezone": "Europe/London",  # STATS19 times are UK local time
            }
            chunk_ids = [c.weather_cell_id for c in chunk]
            try:
                response = http_get(settings.open_meteo_url, params=params)
                payload = response.json()
                payload = payload if isinstance(payload, list) else [payload]
                if len(payload) != len(chunk):
                    raise ValueError(f"expected {len(chunk)} locations, got {len(payload)}")
                for cell, body in zip(chunk, payload):
                    body["requested_cell_id"] = cell.weather_cell_id
                    path = run_dir / f"cell_{cell.weather_cell_id}_{year}.json"
                    path.write_text(json.dumps(body), encoding="utf-8")
                    log_ingestion(run_id=run_id, source="Open-Meteo", dataset=f"hourly_weather_{year}",
                                  url=settings.open_meteo_url, status="SUCCESS", http_status=response.status_code,
                                  row_count=len(body.get("hourly", {}).get("time", [])),
                                  bytes=path.stat().st_size, sha256=_sha256(path),
                                  local_path=str(path.relative_to(settings.data_dir)),
                                  message=f"cell {cell.weather_cell_id}")
                fetched += len(chunk)
            except Exception as exc:  # log and continue - weather enrichment is optional
                failed += len(chunk)
                log_ingestion(run_id=run_id, source="Open-Meteo", dataset=f"hourly_weather_{year}",
                              url=settings.open_meteo_url, status="FAILED",
                              message=f"cells {chunk_ids}: {exc}"[:500])
                logger.error("Weather request failed for %d cells: %s", len(chunk), exc)
            # Pace requests so the per-minute quota is never exceeded.
            weight = open_meteo_weight(len(chunk), (end - start).days + 1, len(WEATHER_VARIABLES))
            time.sleep(max(settings.weather_request_pause_s, 60 * weight / settings.weather_weight_per_minute))

    if cached:
        log_ingestion(run_id=run_id, source="Open-Meteo", dataset="hourly_weather", status="CACHED",
                      row_count=cached, message=f"{cached} cell-year files re-used from earlier runs")
    return {"rows_out": fetched + cached,
            "message": f"weather cell-years fetched={fetched} cached={cached} failed={failed}"}

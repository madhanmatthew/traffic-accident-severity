"""Run metadata, ingestion log and step log.

Every extraction writes one row to `ingestion_log.csv` (source, url, extraction
time, status, row count, bytes, checksum). Every pipeline step writes one row to
`run_log.csv`. Both files are append-only and are loaded into the warehouse as
`etl_ingestion_log` and `etl_run_log`.
"""
from __future__ import annotations

import csv
import functools
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import get_settings

INGESTION_FIELDS = [
    "run_id", "source", "dataset", "url", "extracted_at_utc", "status",
    "http_status", "row_count", "bytes", "sha256", "local_path", "message",
]
RUN_LOG_FIELDS = [
    "run_id", "step", "status", "started_at_utc", "finished_at_utc",
    "duration_s", "rows_in", "rows_out", "message",
]


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_logger(name: str = "traffic_pipeline") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        settings = get_settings()
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(settings.logs_dir / "pipeline.log", encoding="utf-8")
        file_handler.setFormatter(handler.formatter)
        logger.addHandler(file_handler)
    return logger


def _append_csv(path: Path, fields: list[str], row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        if is_new:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fields})


def log_ingestion(**row) -> None:
    row.setdefault("extracted_at_utc", utc_now())
    _append_csv(get_settings().logs_dir / "ingestion_log.csv", INGESTION_FIELDS, row)


def log_step(**row) -> None:
    _append_csv(get_settings().logs_dir / "run_log.csv", RUN_LOG_FIELDS, row)


def pipeline_step(step_name: str):
    """Decorator: time the step, write a run-log row, and re-raise failures.

    The wrapped function must take `run_id` as its first argument and may
    return a dict with `rows_in`, `rows_out` and `message`.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(run_id: str, *args, **kwargs):
            logger = get_logger()
            started = time.perf_counter()
            started_at = utc_now()
            logger.info("[%s] step '%s' started", run_id, step_name)
            try:
                result = func(run_id, *args, **kwargs) or {}
            except Exception as exc:
                log_step(run_id=run_id, step=step_name, status="FAILED", started_at_utc=started_at,
                         finished_at_utc=utc_now(), duration_s=round(time.perf_counter() - started, 2),
                         message=f"{type(exc).__name__}: {exc}"[:500])
                logger.exception("[%s] step '%s' failed", run_id, step_name)
                raise
            duration = round(time.perf_counter() - started, 2)
            log_step(run_id=run_id, step=step_name, status="SUCCESS", started_at_utc=started_at,
                     finished_at_utc=utc_now(), duration_s=duration,
                     rows_in=result.get("rows_in", ""), rows_out=result.get("rows_out", ""),
                     message=result.get("message", ""))
            logger.info("[%s] step '%s' finished in %.1fs %s", run_id, step_name, duration,
                        {k: v for k, v in result.items() if k != "message"})
            return result

        return wrapper

    return decorator

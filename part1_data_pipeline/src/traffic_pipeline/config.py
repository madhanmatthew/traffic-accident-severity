"""Central configuration for the Part 1 data pipeline.

Every value can be overridden with an environment variable (or a `.env` file in
the project root). Credentials such as the database password are never
hard-coded; they are read from DATABASE_URL.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is optional at runtime (Airflow image sets env vars directly)
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")


def _env_list(name: str, default: str) -> list[int]:
    return [int(x) for x in os.getenv(name, default).split(",") if x.strip()]


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "y"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data")))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # --- STATS19 (UK DfT Road Safety Open Data) ---
    stats19_base_url: str = field(default_factory=lambda: os.getenv(
        "STATS19_BASE_URL", "https://data.dft.gov.uk/road-accidents-safety-data"))
    stats19_years: list[int] = field(default_factory=lambda: _env_list("STATS19_YEARS", "2023,2024"))
    # 0 = keep every collision. A positive number draws a reproducible random
    # sample (useful for quick demos on a laptop).
    max_collisions: int = field(default_factory=lambda: int(os.getenv("MAX_COLLISIONS", "0")))
    force_download: bool = field(default_factory=lambda: _env_bool("FORCE_DOWNLOAD", False))

    # --- Open-Meteo historical weather API ---
    weather_enabled: bool = field(default_factory=lambda: _env_bool("WEATHER_ENABLED", True))
    open_meteo_url: str = field(default_factory=lambda: os.getenv(
        "OPEN_METEO_URL", "https://archive-api.open-meteo.com/v1/archive"))
    weather_grid_deg: float = field(default_factory=lambda: float(os.getenv("WEATHER_GRID_DEG", "1.0")))
    weather_locations_per_request: int = field(default_factory=lambda: int(os.getenv("WEATHER_LOCATIONS_PER_REQUEST", "10")))
    # Open-Meteo free tier allows 600 weighted calls per minute; stay below it.
    weather_weight_per_minute: float = field(default_factory=lambda: float(os.getenv("WEATHER_WEIGHT_PER_MINUTE", "500")))
    weather_request_pause_s: float = field(default_factory=lambda: float(os.getenv("WEATHER_REQUEST_PAUSE_S", "2")))
    http_timeout_s: int = field(default_factory=lambda: int(os.getenv("HTTP_TIMEOUT_S", "120")))
    http_retries: int = field(default_factory=lambda: int(os.getenv("HTTP_RETRIES", "4")))

    # Coarse UK bounding box used by the coordinate validation rule.
    uk_lat_min: float = 49.8
    uk_lat_max: float = 61.0
    uk_lon_min: float = -8.7
    uk_lon_max: float = 1.9

    hotspot_grid_deg: float = 0.05

    def __post_init__(self):
        if not self.database_url:
            default_db = self.data_dir / "warehouse" / "traffic_warehouse.db"
            object.__setattr__(self, "database_url", f"sqlite:///{default_db.as_posix()}")

    # Layer folders -----------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def staging_dir(self) -> Path:
        return self.data_dir / "staging"

    @property
    def cleaned_dir(self) -> Path:
        return self.data_dir / "cleaned"

    @property
    def rejected_dir(self) -> Path:
        return self.data_dir / "rejected"

    @property
    def analytics_dir(self) -> Path:
        return self.data_dir / "analytics"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def run_dir(self, layer: str, run_id: str) -> Path:
        path = getattr(self, f"{layer}_dir") / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path


WEATHER_VARIABLES = [
    "temperature_2m",
    "precipitation",
    "rain",
    "snowfall",
    "wind_speed_10m",
    "wind_gusts_10m",
    "cloud_cover",
    "relative_humidity_2m",
    "weather_code",
]


def get_settings() -> Settings:
    return Settings()

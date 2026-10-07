"""Shared fixtures: a small synthetic table with the Part 1 `ml_accident_features` schema.

Synthetic data is only used to unit-test the code paths; real training uses the
STATS19-derived table produced by Part 1.
"""
import numpy as np
import pandas as pd
import pytest
from lightgbm import LGBMClassifier

from severity_model.features import build_pipeline


def make_frame(n: int = 600, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dark = rng.random(n) < 0.3
    speed = rng.choice([20, 30, 40, 60, 70], size=n)
    ped = rng.random(n) < 0.15
    risk = 0.8 * dark + 0.02 * speed + 1.2 * ped + rng.normal(0, 0.6, n)
    severity = np.where(risk > 2.6, 1, np.where(risk > 1.8, 2, 3))
    return pd.DataFrame({
        "collision_index": [f"C{i:05d}" for i in range(n)],
        "collision_datetime": pd.date_range("2023-01-01", periods=n, freq="29h"),
        "weekday": rng.choice(["Monday", "Friday", "Saturday", "Sunday"], size=n),
        "police_force": rng.choice(["Metropolitan Police", "Kent", "Strathclyde"], size=n),
        "nation": rng.choice(["England", "Scotland"], size=n),
        "urban_or_rural": rng.choice(["Urban", "Rural"], size=n),
        "first_road_class": rng.choice(["A", "B", "Motorway"], size=n),
        "road_type": rng.choice(["Single carriageway", "Dual carriageway"], size=n),
        "junction_detail": rng.choice(["Not at junction", "Crossroads"], size=n),
        "junction_control": rng.choice(["Give way or uncontrolled", "Not at junction"], size=n),
        "light_conditions": np.where(dark, "Darkness - no lighting", "Daylight"),
        "weather_conditions": rng.choice(["Fine no high winds", "Raining no high winds"], size=n),
        "road_surface_conditions": rng.choice(["Dry", "Wet or damp"], size=n),
        "special_conditions_at_site": "None", "carriageway_hazards": "None",
        "hour": rng.integers(0, 24, n), "month": rng.integers(1, 13, n),
        "latitude": rng.uniform(50.5, 56.0, n), "longitude": rng.uniform(-4.0, 1.0, n),
        "speed_limit": speed.astype(float),
        "number_of_vehicles": rng.integers(1, 4, n), "number_of_casualties": rng.integers(1, 3, n),
        "temperature_c": rng.normal(10, 5, n), "precipitation_mm": rng.exponential(0.3, n),
        "snowfall_cm": 0.0, "wind_speed_kmh": rng.normal(15, 5, n).clip(0),
        "wind_gusts_kmh": rng.normal(30, 8, n).clip(0), "cloud_cover_pct": rng.uniform(0, 100, n),
        "humidity_pct": rng.uniform(40, 100, n),
        "involves_pedal_cycle": rng.random(n) < 0.1, "involves_motorcycle": rng.random(n) < 0.1,
        "involves_car": rng.random(n) < 0.8, "involves_bus": False, "involves_goods_vehicle": rng.random(n) < 0.1,
        "pedestrian_involved": ped, "mean_driver_age": rng.uniform(18, 80, n),
        "youngest_driver_age": rng.uniform(17, 60, n),
        "severity": severity,
    })


@pytest.fixture(scope="session")
def frame() -> pd.DataFrame:
    return make_frame()


@pytest.fixture(scope="session")
def fitted_pipeline(frame):
    from severity_model.data import to_xy
    X, y = to_xy(frame)
    pipe = build_pipeline(LGBMClassifier(n_estimators=30, verbose=-1, random_state=0))
    pipe.fit(X, y)
    return pipe

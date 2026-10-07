"""Load the model-ready table from Part 1 and split it chronologically."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import get_settings
from .features import RAW_FEATURES, TARGET


@dataclass
class Splits:
    train: pd.DataFrame
    valid: pd.DataFrame
    test: pd.DataFrame

    def describe(self) -> dict:
        out = {}
        for name in ("train", "valid", "test"):
            df = getattr(self, name)
            out[f"{name}_rows"] = len(df)
            out[f"{name}_start"] = str(df["collision_datetime"].min())
            out[f"{name}_end"] = str(df["collision_datetime"].max())
            for code, share in df[TARGET].value_counts(normalize=True).sort_index().items():
                out[f"{name}_share_class{code}"] = round(float(share), 4)
        return out


def load_features() -> pd.DataFrame:
    settings = get_settings()
    if settings.features_database_url:
        from sqlalchemy import create_engine
        df = pd.read_sql("SELECT * FROM ml_accident_features", create_engine(settings.features_database_url))
    else:
        if not settings.features_path.exists():
            raise FileNotFoundError(
                f"{settings.features_path} not found - run the Part 1 pipeline first "
                "or set FEATURES_PATH / FEATURES_DATABASE_URL")
        df = pd.read_parquet(settings.features_path)
    df["collision_datetime"] = pd.to_datetime(df["collision_datetime"])
    missing = [c for c in [*RAW_FEATURES, TARGET] if c not in df.columns]
    if missing:
        raise ValueError(f"model-ready table is missing columns: {missing}")
    return df.sort_values("collision_datetime").reset_index(drop=True)


def chronological_split(df: pd.DataFrame, train_end: str | None = None, valid_end: str | None = None) -> Splits:
    """Train on the past, validate on the following period, test on the most recent period.

    A random split would leak future patterns (seasonality, reporting changes)
    into training and overstate performance.
    """
    settings = get_settings()
    train_end = pd.Timestamp(train_end or settings.train_end) + pd.Timedelta(days=1)
    valid_end = pd.Timestamp(valid_end or settings.valid_end) + pd.Timedelta(days=1)
    ts = df["collision_datetime"]
    splits = Splits(train=df[ts < train_end], valid=df[(ts >= train_end) & (ts < valid_end)], test=df[ts >= valid_end])
    for name in ("train", "valid", "test"):
        if getattr(splits, name).empty:
            raise ValueError(f"{name} split is empty - check TRAIN_END/VALID_END against the data period")
    return splits


def to_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Features and 0-based label (0 Fatal, 1 Serious, 2 Slight)."""
    return df[RAW_FEATURES].copy(), (df[TARGET].astype(int) - 1)

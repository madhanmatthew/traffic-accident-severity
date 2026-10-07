"""Feature engineering + preprocessing, packaged with the model as ONE sklearn Pipeline.

The serving API passes raw accident fields (the same columns as the Part 1
`ml_accident_features` table); everything else - derived features,
imputation, one-hot encoding - happens inside the pipeline, so training and
inference can never diverge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

TARGET = "severity"

CATEGORICAL_FEATURES = [
    "weekday", "police_force", "nation", "urban_or_rural", "first_road_class", "road_type",
    "junction_detail", "junction_control", "light_conditions", "weather_conditions",
    "road_surface_conditions", "special_conditions_at_site", "carriageway_hazards",
]
NUMERIC_FEATURES = [
    "hour", "month", "latitude", "longitude", "speed_limit", "number_of_vehicles", "number_of_casualties",
    "temperature_c", "precipitation_mm", "snowfall_cm", "wind_speed_kmh", "wind_gusts_kmh",
    "cloud_cover_pct", "humidity_pct", "mean_driver_age", "youngest_driver_age",
]
BOOLEAN_FEATURES = [
    "involves_pedal_cycle", "involves_motorcycle", "involves_car", "involves_bus",
    "involves_goods_vehicle", "pedestrian_involved",
]
RAW_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES + BOOLEAN_FEATURES

DERIVED_FEATURES = [
    "hour_sin", "hour_cos", "month_sin", "month_cos", "is_weekend", "is_dark", "is_dark_unlit",
    "is_wet_or_icy", "measured_rain", "is_freezing", "high_speed_road", "at_junction",
    "single_vehicle", "young_driver", "vulnerable_road_user", "speed_x_vehicles", "casualties_per_vehicle",
]


class AccidentFeatureEngineer(BaseEstimator, TransformerMixin):
    """Adds domain features derived from the raw accident fields (stateless)."""

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = pd.DataFrame(X).copy()
        for col in RAW_FEATURES:  # tolerate partially filled API payloads
            if col not in X:
                X[col] = np.nan
        for col in NUMERIC_FEATURES:
            X[col] = pd.to_numeric(X[col], errors="coerce").astype(float)
        for col in BOOLEAN_FEATURES:
            X[col] = X[col].map(lambda v: 1.0 if v in (True, 1, "true", "True") else
                                (0.0 if v in (False, 0, "false", "False") else np.nan)).astype(float)
        for col in CATEGORICAL_FEATURES:
            X[col] = X[col].astype("object").where(X[col].notna(), "Unknown").astype(str)

        hour, month = X["hour"], X["month"]
        X["hour_sin"], X["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
        X["month_sin"], X["month_cos"] = np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12)
        X["is_weekend"] = X["weekday"].isin(["Saturday", "Sunday"]).astype(float)
        X["is_dark"] = X["light_conditions"].str.startswith("Darkness").astype(float)
        X["is_dark_unlit"] = X["light_conditions"].isin(["Darkness - lights unlit", "Darkness - no lighting"]).astype(float)
        X["is_wet_or_icy"] = X["road_surface_conditions"].isin(
            ["Wet or damp", "Snow", "Frost or ice", "Flood over 3cm deep"]).astype(float)
        X["measured_rain"] = (X["precipitation_mm"] > 0.1).astype(float).where(X["precipitation_mm"].notna())
        X["is_freezing"] = (X["temperature_c"] <= 0).astype(float).where(X["temperature_c"].notna())
        X["high_speed_road"] = (X["speed_limit"] >= 60).astype(float).where(X["speed_limit"].notna())
        X["at_junction"] = (~X["junction_detail"].isin(["Not at junction", "Unknown"])).astype(float)
        X["single_vehicle"] = (X["number_of_vehicles"] == 1).astype(float)
        X["young_driver"] = (X["youngest_driver_age"] < 25).astype(float).where(X["youngest_driver_age"].notna())
        X["vulnerable_road_user"] = X[["involves_pedal_cycle", "involves_motorcycle", "pedestrian_involved"]] \
            .max(axis=1)
        X["speed_x_vehicles"] = X["speed_limit"] * X["number_of_vehicles"]
        X["casualties_per_vehicle"] = X["number_of_casualties"] / X["number_of_vehicles"].clip(lower=1)
        return X

    def get_feature_names_out(self, input_features=None):
        return np.array(RAW_FEATURES + DERIVED_FEATURES)


def build_preprocessor() -> ColumnTransformer:
    numeric = NUMERIC_FEATURES + BOOLEAN_FEATURES + DERIVED_FEATURES
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="Unknown")),
        ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=30, sparse_output=False)),
    ])
    return ColumnTransformer([
        ("num", SimpleImputer(strategy="median", add_indicator=True), numeric),
        ("cat", categorical, CATEGORICAL_FEATURES),
    ], verbose_feature_names_out=False)


def build_pipeline(estimator) -> Pipeline:
    """Feature engineering -> preprocessing -> classifier, as one deployable object."""
    return Pipeline([
        ("features", AccidentFeatureEngineer()),
        ("preprocess", build_preprocessor()),
        ("model", estimator),
    ])

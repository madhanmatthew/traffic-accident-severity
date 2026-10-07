import numpy as np
import pandas as pd
import pytest

from severity_model import evaluate as ev
from severity_model.data import chronological_split, to_xy
from severity_model.features import DERIVED_FEATURES, RAW_FEATURES, AccidentFeatureEngineer
from severity_model.train import class_weights


def test_feature_engineer_adds_derived_columns_and_tolerates_missing(frame):
    out = AccidentFeatureEngineer().transform(frame[RAW_FEATURES].head(5).drop(columns=["temperature_c"]))
    assert set(DERIVED_FEATURES) <= set(out.columns)
    assert out["is_freezing"].isna().all()  # missing temperature stays missing, not "not freezing"
    assert out["hour_sin"].between(-1, 1).all()


def test_chronological_split_has_no_overlap(frame):
    s = chronological_split(frame, train_end="2023-12-31", valid_end="2024-03-31")
    assert s.train["collision_datetime"].max() < s.valid["collision_datetime"].min()
    assert s.valid["collision_datetime"].max() < s.test["collision_datetime"].min()
    assert len(s.train) + len(s.valid) + len(s.test) == len(frame)


def test_class_weights_upweight_rare_classes():
    y = pd.Series([0] * 10 + [1] * 30 + [2] * 160)
    w = class_weights(y, 1.0)
    assert w[0] > w[10] > w[-1]
    np.testing.assert_allclose(pd.Series(w).groupby(y).sum().to_numpy(), [200 / 3] * 3)
    assert class_weights(y, 0.5)[0] == pytest.approx(np.sqrt(w[0]))


def test_pipeline_predicts_from_raw_fields(fitted_pipeline, frame):
    X, _ = to_xy(frame.head(10))
    proba = fitted_pipeline.predict_proba(X)
    assert proba.shape == (10, 3)
    np.testing.assert_allclose(proba.sum(axis=1), 1.0)


def test_unseen_category_does_not_break_inference(fitted_pipeline, frame):
    X, _ = to_xy(frame.head(2))
    X["police_force"] = "Brand New Force"
    X["road_type"] = None
    assert fitted_pipeline.predict(X).shape == (2,)


def test_ksi_false_negative_rate():
    y_true = [0, 1, 1, 2, 2]
    y_pred = [2, 1, 0, 2, 0]  # one KSI predicted slight out of 3 KSI
    assert ev.ksi_false_negative_rate(y_true, y_pred) == pytest.approx(1 / 3)
    m = ev.compute_metrics(y_true, y_pred)
    assert m["ksi_recall"] == pytest.approx(2 / 3, abs=1e-4)
    assert {"macro_f1", "recall_fatal", "recall_serious", "recall_slight"} <= set(m)

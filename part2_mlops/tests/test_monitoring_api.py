import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from severity_model import monitoring as mon
from severity_model.data import to_xy
from severity_model.features import RAW_FEATURES
from severity_model.registry import export_champion


def test_psi_is_zero_for_identical_and_large_for_shifted():
    assert mon.psi([0.5, 0.5], [0.5, 0.5]) == pytest.approx(0)
    assert mon.psi([0.9, 0.1], [0.1, 0.9]) > 1


def test_report_flags_simulated_drift(frame, fitted_pipeline):
    X, y = to_xy(frame)
    profile = mon.build_profile(X, y, fitted_pipeline.predict(X))
    baseline = {"test_macro_f1": 0.9, "test_ksi_false_negative_rate": 0.1}

    same = mon.build_report(X, fitted_pipeline.predict(X), profile, baseline, y_true=y)
    assert all(d["psi"] < 0.1 for d in same["feature_drift"])

    shifted = mon.simulate_drift(frame)
    Xs, ys = to_xy(shifted)
    drifted = mon.build_report(Xs, fitted_pipeline.predict(Xs), profile, baseline, y_true=ys)
    assert drifted["retraining"]["required"]
    significant = {d["feature"] for d in drifted["feature_drift"] if d["status"] == "significant"}
    assert {"light_conditions", "hour"} <= significant


@pytest.fixture()
def client(tmp_path, monkeypatch, frame, fitted_pipeline):
    X, y = to_xy(frame)
    export_champion(fitted_pipeline,
                    {"version": "test", "metrics": {}, "trained_at": "2026-01-01T00:00:00+00:00"},
                    mon.build_profile(X, y, fitted_pipeline.predict(X)), tmp_path / "champion")
    monkeypatch.setenv("CHAMPION_DIR", str(tmp_path / "champion"))
    monkeypatch.setenv("PREDICTION_LOG_PATH", str(tmp_path / "predictions.jsonl"))
    monkeypatch.delenv("MODEL_URI", raising=False)
    from severity_model.api import app
    with TestClient(app) as c:
        yield c


def payload(frame) -> dict:
    row = frame[RAW_FEATURES].iloc[0].to_dict()
    return {k: (v.item() if isinstance(v, np.generic) else v) for k, v in row.items()}


def test_api_predict_logs_and_reports_metrics(client, frame, tmp_path):
    assert client.get("/health").json()["status"] == "ok"
    r = client.post("/predict", json=payload(frame))
    assert r.status_code == 200
    body = r.json()
    assert body["predicted_severity"] in {"Fatal", "Serious", "Slight"}
    assert sum(body["probabilities"].values()) == pytest.approx(1, abs=1e-3)

    batch = client.post("/predict/batch", json={"records": [payload(frame)] * 3})
    assert batch.status_code == 200 and len(batch.json()) == 3

    bad = payload(frame) | {"hour": 31}
    assert client.post("/predict", json=bad).status_code == 422

    metrics = client.get("/metrics").json()
    assert metrics["requests"] == 5 and metrics["errors"] == 1
    lines = (tmp_path / "predictions.jsonl").read_text().splitlines()
    statuses = [json.loads(line)["status"] for line in lines]
    assert statuses.count("ok") == 4 and statuses.count("invalid_input") == 1

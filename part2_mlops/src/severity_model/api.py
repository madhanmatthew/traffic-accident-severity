"""FastAPI inference service for the accident severity model.

    uvicorn severity_model.api:app --host 0.0.0.0 --port 8000

Endpoints
  GET  /health          liveness + model loaded?
  GET  /model-info      registry version, training window, test metrics
  POST /predict         one collision -> severity class + probabilities
  POST /predict/batch   up to 1,000 collisions
  GET  /metrics         request count, error rate, latency percentiles, class mix

Every request (inputs, prediction, latency, status) is appended to the
prediction log (JSONL); the monitoring job reads it for drift/latency checks.
By default the model is loaded from models/champion/ (baked into the Docker
image). Set MODEL_URI=models:/traffic-severity-classifier@champion to load
straight from the MLflow registry instead.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import CLASS_NAMES, get_settings
from .features import RAW_FEATURES


class AccidentInput(BaseModel):
    """Raw collision attributes known when the collision is reported."""
    hour: int = Field(..., ge=0, le=23, examples=[17])
    month: int = Field(..., ge=1, le=12, examples=[11])
    weekday: str = Field(..., examples=["Friday"])
    latitude: float = Field(..., ge=49.8, le=61.0, examples=[51.5074])
    longitude: float = Field(..., ge=-8.7, le=1.9, examples=[-0.1278])
    police_force: str = Field("Unknown", examples=["Metropolitan Police"])
    nation: str = Field("Unknown", examples=["England"])
    urban_or_rural: str = Field("Unknown", examples=["Urban"])
    first_road_class: str = Field("Unknown", examples=["A"])
    road_type: str = Field("Unknown", examples=["Single carriageway"])
    speed_limit: Optional[float] = Field(None, ge=10, le=70, examples=[30])
    junction_detail: str = Field("Unknown", examples=["T or staggered junction"])
    junction_control: str = Field("Unknown", examples=["Give way or uncontrolled"])
    light_conditions: str = Field("Unknown", examples=["Darkness - lights lit"])
    weather_conditions: str = Field("Unknown", examples=["Raining no high winds"])
    road_surface_conditions: str = Field("Unknown", examples=["Wet or damp"])
    special_conditions_at_site: str = Field("None", examples=["None"])
    carriageway_hazards: str = Field("None", examples=["None"])
    number_of_vehicles: int = Field(..., ge=1, le=100, examples=[2])
    number_of_casualties: int = Field(..., ge=1, le=100, examples=[1])
    temperature_c: Optional[float] = Field(None, ge=-35, le=45, examples=[8.5])
    precipitation_mm: Optional[float] = Field(None, ge=0, le=150, examples=[1.2])
    snowfall_cm: Optional[float] = Field(None, ge=0, le=50, examples=[0.0])
    wind_speed_kmh: Optional[float] = Field(None, ge=0, le=250, examples=[18.0])
    wind_gusts_kmh: Optional[float] = Field(None, ge=0, le=300, examples=[35.0])
    cloud_cover_pct: Optional[float] = Field(None, ge=0, le=100, examples=[90])
    humidity_pct: Optional[float] = Field(None, ge=0, le=100, examples=[88])
    involves_pedal_cycle: bool = False
    involves_motorcycle: bool = False
    involves_car: bool = True
    involves_bus: bool = False
    involves_goods_vehicle: bool = False
    pedestrian_involved: bool = False
    mean_driver_age: Optional[float] = Field(None, ge=0, le=110, examples=[38])
    youngest_driver_age: Optional[float] = Field(None, ge=0, le=110, examples=[24])


class Prediction(BaseModel):
    predicted_severity: str
    probabilities: dict[str, float]
    ksi_probability: float = Field(..., description="P(Fatal) + P(Serious)")
    model_version: str
    latency_ms: float


class BatchRequest(BaseModel):
    records: list[AccidentInput] = Field(..., min_length=1, max_length=1000)


class ServiceState:
    def __init__(self):
        self.model = None
        self.metadata: dict = {}
        self.lock = threading.Lock()
        self.requests = 0
        self.errors = 0
        self.latencies: deque[float] = deque(maxlen=5000)
        self.classes: Counter = Counter()
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def load(self):
        model_uri = os.getenv("MODEL_URI")
        if model_uri:
            import mlflow
            mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
            self.model = mlflow.sklearn.load_model(model_uri)
            self.metadata = {"model_uri": model_uri, "version": model_uri}
        else:
            from .registry import load_champion
            champion = load_champion()
            self.model, self.metadata = champion.model, champion.metadata

    def log(self, record: dict) -> None:
        path = get_settings().prediction_log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")


state = ServiceState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.load()
    yield


app = FastAPI(title="Traffic Accident Severity API", version="1.0.0", lifespan=lifespan,
              description="Predicts STATS19 collision severity (Fatal / Serious / Slight).")


@app.exception_handler(RequestValidationError)
async def invalid_input(_: Request, exc: RequestValidationError):
    """Count and log rejected payloads - a rising rate signals an upstream data-quality problem."""
    detail = jsonable_encoder(exc.errors())
    state.requests += 1
    state.errors += 1
    state.log({"timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
               "status": "invalid_input", "error": json.dumps(detail, default=str)[:500]})
    return JSONResponse(status_code=422, content={"detail": detail})


def _predict(records: list[AccidentInput]) -> list[Prediction]:
    started = time.perf_counter()
    frame = pd.DataFrame([r.model_dump() for r in records])[RAW_FEATURES]
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    try:
        proba = state.model.predict_proba(frame)
    except Exception as exc:
        state.errors += len(records)
        state.requests += len(records)
        for r in records:
            state.log({"timestamp": now, "status": "error", "error": str(exc)[:300], "input": r.model_dump()})
        raise HTTPException(status_code=500, detail=f"prediction failed: {exc}") from exc

    latency = (time.perf_counter() - started) * 1000 / len(records)
    version = str(state.metadata.get("version", "unknown"))
    out = []
    for record, p in zip(records, proba):
        label = CLASS_NAMES[int(np.argmax(p))]
        pred = Prediction(predicted_severity=label,
                          probabilities={c: round(float(v), 5) for c, v in zip(CLASS_NAMES, p)},
                          ksi_probability=round(float(p[0] + p[1]), 5), model_version=version,
                          latency_ms=round(latency, 2))
        out.append(pred)
        state.classes[label] += 1
        state.latencies.append(latency)
        state.log({"timestamp": now, "status": "ok", "model_version": version, "latency_ms": pred.latency_ms,
                   "predicted_severity": label, "probabilities": pred.probabilities, "input": record.model_dump()})
    state.requests += len(records)
    return out


@app.get("/health")
def health():
    return {"status": "ok" if state.model is not None else "model not loaded",
            "model_version": state.metadata.get("version"), "started_at": state.started_at}


@app.get("/model-info")
def model_info():
    return state.metadata


@app.post("/predict", response_model=Prediction)
def predict(record: AccidentInput):
    return _predict([record])[0]


@app.post("/predict/batch", response_model=list[Prediction])
def predict_batch(batch: BatchRequest):
    return _predict(batch.records)


@app.get("/metrics")
def metrics():
    lat = np.array(state.latencies) if state.latencies else np.array([np.nan])
    return {
        "requests": state.requests, "errors": state.errors,
        "error_rate": round(state.errors / state.requests, 4) if state.requests else 0.0,
        "latency_ms": {"p50": round(float(np.nanpercentile(lat, 50)), 2) if state.latencies else None,
                       "p95": round(float(np.nanpercentile(lat, 95)), 2) if state.latencies else None,
                       "p99": round(float(np.nanpercentile(lat, 99)), 2) if state.latencies else None},
        "predicted_class_counts": dict(state.classes),
        "model_version": state.metadata.get("version"),
    }

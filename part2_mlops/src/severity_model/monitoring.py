"""Model monitoring: data quality, feature/class/location drift, performance, latency.

    # labelled batch (e.g. the newest month of Part 1 data) - full report incl. performance
    python -m severity_model.monitoring --current path/to/ml_accident_features.parquet --since 2024-10-01
    # unlabelled production traffic captured by the API
    python -m severity_model.monitoring --prediction-log logs/predictions.jsonl
    # demo: a deliberately shifted batch to show the alarms firing
    python -m severity_model.monitoring --simulate-drift

Drift is measured with the Population Stability Index (PSI) against the
reference profile saved at training time:
    PSI < 0.1 stable | 0.1-0.2 moderate | > 0.2 significant.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CLASS_NAMES, RetrainingPolicy, get_settings
from .evaluate import compute_metrics
from .features import BOOLEAN_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES, RAW_FEATURES, TARGET

EPS = 1e-4
KEY_FEATURES = ["hour", "speed_limit", "number_of_vehicles", "number_of_casualties", "temperature_c",
                "precipitation_mm", "light_conditions", "road_surface_conditions", "urban_or_rural",
                "first_road_class", "weather_conditions", "pedestrian_involved", "involves_motorcycle"]
LOCATION_FEATURES = ["police_force", "nation"]


# --------------------------------------------------------------------------- profiles
def _numeric_profile(s: pd.Series) -> dict:
    s = pd.to_numeric(s, errors="coerce")
    valid = s.dropna()
    edges = np.unique(np.quantile(valid, np.linspace(0, 1, 11))) if len(valid) else np.array([0.0])
    inner = edges[1:-1].tolist()
    counts = np.histogram(valid, bins=[-np.inf, *inner, np.inf])[0] if len(valid) else np.array([0])
    return {
        "type": "numeric", "inner_edges": inner,
        "proportions": (counts / max(counts.sum(), 1)).tolist(),
        "missing_rate": float(s.isna().mean()),
        "min": float(valid.min()) if len(valid) else None, "max": float(valid.max()) if len(valid) else None,
        "mean": float(valid.mean()) if len(valid) else None,
    }


def _categorical_profile(s: pd.Series) -> dict:
    s = s.astype("object")
    missing = s.isna() | s.isin(["Unknown"])
    return {"type": "categorical",
            "proportions": s.fillna("Unknown").astype(str).value_counts(normalize=True).round(6).to_dict(),
            "missing_rate": float(missing.mean())}


def build_profile(X: pd.DataFrame, y: pd.Series | None = None, y_pred: np.ndarray | None = None) -> dict:
    """Reference statistics saved with the model at training time."""
    profile = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": len(X),
               "features": {}}
    for col in NUMERIC_FEATURES:
        profile["features"][col] = _numeric_profile(X[col])
    for col in CATEGORICAL_FEATURES + BOOLEAN_FEATURES:
        profile["features"][col] = _categorical_profile(X[col].astype("object"))
    if y is not None:
        profile["class_distribution"] = _class_distribution(y)
    if y_pred is not None:
        profile["prediction_distribution"] = _class_distribution(y_pred)
    profile["location_centroid"] = {"latitude": float(pd.to_numeric(X["latitude"]).mean()),
                                    "longitude": float(pd.to_numeric(X["longitude"]).mean())}
    return profile


def _class_distribution(labels) -> dict[str, float]:
    counts = pd.Series(np.asarray(labels)).value_counts(normalize=True)
    return {name: float(counts.get(i, 0.0)) for i, name in enumerate(CLASS_NAMES)}


# --------------------------------------------------------------------------- PSI
def psi(expected: list[float] | np.ndarray, actual: list[float] | np.ndarray) -> float:
    e = np.clip(np.asarray(expected, dtype=float), EPS, None)
    a = np.clip(np.asarray(actual, dtype=float), EPS, None)
    return float(np.sum((a - e) * np.log(a / e)))


def feature_psi(ref: dict, current: pd.Series) -> float:
    if ref["type"] == "numeric":
        values = pd.to_numeric(current, errors="coerce").dropna()
        if values.empty:
            return float("nan")
        counts = np.histogram(values, bins=[-np.inf, *ref["inner_edges"], np.inf])[0]
        return psi(ref["proportions"], counts / counts.sum())
    cur = current.astype("object").fillna("Unknown").astype(str).value_counts(normalize=True)
    cats = sorted(set(ref["proportions"]) | set(cur.index))
    return psi([ref["proportions"].get(c, 0.0) for c in cats], [cur.get(c, 0.0) for c in cats])


def distribution_psi(ref: dict[str, float], cur: dict[str, float]) -> float:
    keys = sorted(set(ref) | set(cur))
    return psi([ref.get(k, 0.0) for k in keys], [cur.get(k, 0.0) for k in keys])


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------- report
def data_quality(profile: dict, X: pd.DataFrame) -> dict:
    rows = []
    for col in RAW_FEATURES:
        ref = profile["features"][col]
        series = X[col] if col in X else pd.Series(np.nan, index=X.index)
        if ref["type"] == "numeric":
            values = pd.to_numeric(series, errors="coerce")
            missing = float(values.isna().mean())
            out_of_range = float(((values < ref["min"]) | (values > ref["max"])).mean()) if ref["min"] is not None else 0
            unseen = 0.0
        else:
            values = series.astype("object")
            missing = float((values.isna() | values.isin(["Unknown"])).mean())
            out_of_range = 0.0
            seen = values.fillna("Unknown").astype(str).isin(ref["proportions"].keys())
            unseen = float((~seen).mean()) if len(values) else 0.0
        rows.append({"feature": col, "missing_rate": round(missing, 4),
                     "reference_missing_rate": round(ref["missing_rate"], 4),
                     "missing_rate_increase": round(missing - ref["missing_rate"], 4),
                     "out_of_range_rate": round(out_of_range, 4), "unseen_category_rate": round(unseen, 4)})
    return {"features": rows}


def api_operational_metrics(log_path: Path) -> dict | None:
    if not log_path.exists():
        return None
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        return None
    df = pd.DataFrame(records)
    ok = df[df["status"] == "ok"]
    return {
        "requests": len(df),
        "error_rate": round(float((df["status"] != "ok").mean()), 4),
        "latency_p50_ms": round(float(ok["latency_ms"].quantile(0.5)), 2) if len(ok) else None,
        "latency_p95_ms": round(float(ok["latency_ms"].quantile(0.95)), 2) if len(ok) else None,
        "latency_max_ms": round(float(ok["latency_ms"].max()), 2) if len(ok) else None,
        "first_request": df["timestamp"].min(), "last_request": df["timestamp"].max(),
    }


def build_report(X: pd.DataFrame, y_pred: np.ndarray, profile: dict, baseline: dict,
                 y_true: pd.Series | None = None, api_log: Path | None = None,
                 model_trained_at: str | None = None, policy: RetrainingPolicy | None = None) -> dict:
    policy = policy or RetrainingPolicy()
    report: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "rows": len(X), "policy": policy.__dict__}

    # ---- input data quality
    report["data_quality"] = data_quality(profile, X)

    # ---- feature drift
    drift = []
    for col in RAW_FEATURES:
        value = feature_psi(profile["features"][col], X[col]) if col in X else float("nan")
        drift.append({"feature": col, "psi": round(value, 4), "key_feature": col in KEY_FEATURES,
                      "status": "n/a" if np.isnan(value) else
                      ("significant" if value > 0.2 else "moderate" if value > 0.1 else "stable")})
    report["feature_drift"] = sorted(drift, key=lambda d: -(d["psi"] if not np.isnan(d["psi"]) else -1))

    # ---- class drift (predictions always; actual labels when available)
    pred_dist = _class_distribution(y_pred)
    class_section = {"prediction_distribution": pred_dist,
                     "reference_prediction_distribution": profile.get("prediction_distribution"),
                     "prediction_psi": round(distribution_psi(profile["prediction_distribution"], pred_dist), 4)}
    if y_true is not None:
        actual = _class_distribution(y_true)
        class_section.update({"actual_distribution": actual,
                              "reference_actual_distribution": profile["class_distribution"],
                              "actual_psi": round(distribution_psi(profile["class_distribution"], actual), 4)})
    report["class_drift"] = class_section

    # ---- location drift
    loc = {col: round(feature_psi(profile["features"][col], X[col]), 4) for col in LOCATION_FEATURES}
    ref_c = profile["location_centroid"]
    lat, lon = pd.to_numeric(X["latitude"]).mean(), pd.to_numeric(X["longitude"]).mean()
    loc["centroid_shift_km"] = round(_haversine_km(ref_c["latitude"], ref_c["longitude"], lat, lon), 2)
    report["location_drift"] = loc

    # ---- performance (needs ground truth)
    if y_true is not None:
        perf = compute_metrics(y_true, y_pred)
        perf["baseline_macro_f1"] = baseline.get("test_macro_f1")
        perf["baseline_ksi_false_negative_rate"] = baseline.get("test_ksi_false_negative_rate")
        report["performance"] = perf

    # ---- operational
    if api_log is not None:
        report["operational"] = api_operational_metrics(api_log)

    report["retraining"] = retraining_decision(report, policy, model_trained_at)
    return report


def retraining_decision(report: dict, policy: RetrainingPolicy, model_trained_at: str | None) -> dict:
    reasons, warnings = [], []
    drifted = [d["feature"] for d in report["feature_drift"]
               if d["key_feature"] and not np.isnan(d["psi"]) and d["psi"] > policy.feature_psi_threshold]
    if len(drifted) > policy.max_drifted_features:
        reasons.append(f"{len(drifted)} key features drifted (PSI > {policy.feature_psi_threshold}): {drifted}")
    elif drifted:
        warnings.append(f"feature drift on {drifted}")

    cls = report["class_drift"]
    class_psi = cls.get("actual_psi", cls["prediction_psi"])
    if class_psi > policy.class_psi_threshold:
        reasons.append(f"class distribution drift PSI={class_psi:.3f} > {policy.class_psi_threshold}")

    loc_psi = report["location_drift"]["police_force"]
    if loc_psi > policy.location_psi_threshold:
        reasons.append(f"location drift (police force PSI={loc_psi:.3f} > {policy.location_psi_threshold})")

    dq_bad = [f["feature"] for f in report["data_quality"]["features"]
              if f["missing_rate_increase"] > policy.max_missing_rate_increase]
    if dq_bad:
        warnings.append(f"input data-quality alarm - missing-rate increase on {dq_bad} (fix upstream before retraining)")

    perf = report.get("performance")
    if perf and perf.get("baseline_macro_f1") is not None:
        if perf["baseline_macro_f1"] - perf["macro_f1"] > policy.macro_f1_drop:
            reasons.append(f"macro-F1 dropped {perf['baseline_macro_f1']:.3f} -> {perf['macro_f1']:.3f}")
        if perf["ksi_false_negative_rate"] - perf["baseline_ksi_false_negative_rate"] > policy.ksi_fnr_increase:
            reasons.append(f"KSI false-negative rate rose {perf['baseline_ksi_false_negative_rate']:.3f} -> "
                           f"{perf['ksi_false_negative_rate']:.3f}")

    ops = report.get("operational")
    if ops:
        if ops["error_rate"] > policy.max_error_rate:
            warnings.append(f"API error rate {ops['error_rate']:.2%} > {policy.max_error_rate:.0%}")
        if ops["latency_p95_ms"] and ops["latency_p95_ms"] > policy.max_p95_latency_ms:
            warnings.append(f"API p95 latency {ops['latency_p95_ms']} ms > {policy.max_p95_latency_ms} ms")

    if model_trained_at:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(model_trained_at)).days
        if age > policy.max_model_age_days:
            reasons.append(f"model is {age} days old (> {policy.max_model_age_days})")

    return {"required": bool(reasons), "reasons": reasons, "warnings": warnings}


def report_markdown(report: dict) -> str:
    r = report["retraining"]
    lines = [f"# Model monitoring report - {report['generated_at']}", "",
             f"Rows analysed: **{report['rows']:,}**", "",
             f"## Decision: {'RETRAIN' if r['required'] else 'no retraining needed'}", ""]
    lines += [f"- {x}" for x in r["reasons"]] or ["- no retraining criteria met"]
    if r["warnings"]:
        lines += ["", "**Warnings**", *[f"- {w}" for w in r["warnings"]]]
    lines += ["", "## Class drift", "", "```json", json.dumps(report["class_drift"], indent=2), "```",
              "", "## Location drift", "", "```json", json.dumps(report["location_drift"], indent=2), "```",
              "", "## Feature drift (top 15 by PSI)", "", "| feature | PSI | status |", "|---|---|---|"]
    lines += [f"| {d['feature']} | {d['psi']} | {d['status']} |" for d in report["feature_drift"][:15]]
    if "performance" in report:
        p = report["performance"]
        lines += ["", "## Performance (labelled batch)", "",
                  f"- macro-F1: {p['macro_f1']:.4f} (baseline {p['baseline_macro_f1']})",
                  f"- KSI false-negative rate: {p['ksi_false_negative_rate']:.4f} "
                  f"(baseline {p['baseline_ksi_false_negative_rate']})",
                  f"- recall Fatal / Serious / Slight: {p['recall_fatal']:.3f} / {p['recall_serious']:.3f} / "
                  f"{p['recall_slight']:.3f}"]
    if report.get("operational"):
        lines += ["", "## API operations", "", "```json", json.dumps(report["operational"], indent=2), "```"]
    return "\n".join(lines) + "\n"


def save_report(report: dict, name: str) -> Path:
    settings = get_settings()
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = settings.reports_dir / f"monitoring_{name}_{stamp}.json"
    text = json.dumps(report, indent=2, default=str)
    json_path.write_text(text, encoding="utf-8")
    (settings.reports_dir / "latest_monitoring.json").write_text(text, encoding="utf-8")
    json_path.with_suffix(".md").write_text(report_markdown(report), encoding="utf-8")
    return json_path


# --------------------------------------------------------------------------- CLI
def simulate_drift(df: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Shifted batch for demonstration: rural Scotland/Wales at night in wet, cold weather."""
    rng = np.random.default_rng(seed)
    shifted = df[df["nation"].isin(["Scotland", "Wales"]) | (df["urban_or_rural"] == "Rural")].copy()
    shifted = shifted.sample(frac=1.0, random_state=seed)
    n = len(shifted)
    shifted["light_conditions"] = rng.choice(["Darkness - no lighting", "Darkness - lights lit", "Daylight"],
                                             size=n, p=[0.5, 0.3, 0.2])
    shifted["road_surface_conditions"] = rng.choice(["Wet or damp", "Frost or ice", "Dry"], size=n, p=[0.6, 0.2, 0.2])
    shifted["temperature_c"] = shifted["temperature_c"] - 8
    shifted["precipitation_mm"] = shifted["precipitation_mm"].fillna(0) + rng.gamma(1.5, 1.0, size=n)
    shifted["hour"] = rng.choice([0, 1, 2, 3, 4, 5, 21, 22, 23], size=n)
    return shifted


def main(argv: list[str] | None = None) -> int:
    from .registry import load_champion

    parser = argparse.ArgumentParser(description="Monitor the champion severity model")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--current", type=Path, help="labelled Parquet batch (ml_accident_features schema)")
    src.add_argument("--prediction-log", type=Path, help="API prediction log (JSONL, unlabelled)")
    src.add_argument("--simulate-drift", action="store_true", help="demo with a deliberately shifted batch")
    parser.add_argument("--since", help="only rows with collision_datetime >= this date (labelled batches)")
    args = parser.parse_args(argv)

    settings = get_settings()
    champion = load_champion()
    y_true = None

    if args.prediction_log:
        records = [json.loads(line) for line in args.prediction_log.read_text(encoding="utf-8").splitlines() if line]
        ok = [r for r in records if r.get("status") == "ok"]
        if not ok:
            raise SystemExit("no successful predictions in the log yet")
        X = pd.DataFrame([r["input"] for r in ok])
        y_pred = np.array([CLASS_NAMES.index(r["predicted_severity"]) for r in ok])
        name = "prediction_log"
    else:
        from .data import load_features
        df = pd.read_parquet(args.current) if args.current else load_features()
        df["collision_datetime"] = pd.to_datetime(df["collision_datetime"])
        since = args.since or settings.valid_end
        df = df[df["collision_datetime"] > pd.Timestamp(since)]
        if args.simulate_drift:
            df = simulate_drift(df)
        X, y_true = df[RAW_FEATURES], df[TARGET].astype(int) - 1
        y_pred = champion.model.predict(X)
        name = "simulated_drift" if args.simulate_drift else "labelled_batch"

    report = build_report(X, y_pred, champion.profile, champion.metadata["metrics"], y_true=y_true,
                          api_log=settings.prediction_log_path, model_trained_at=champion.metadata["trained_at"])
    path = save_report(report, name)
    print(report_markdown(report))
    print(f"report written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

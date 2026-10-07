"""Streamlit front-end for the severity model: live prediction, model card, monitoring.

    streamlit run dashboard/app.py      (expects the API on API_URL, default http://localhost:8000)

Deliberately talks to the model only through the FastAPI service, exactly as
any other consumer would.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", ROOT / "reports"))
CHAMPION_DIR = Path(os.getenv("CHAMPION_DIR", ROOT / "models" / "champion"))
COLORS = {"Fatal": "#b2182b", "Serious": "#ef8a62", "Slight": "#67a9cf"}

st.set_page_config(page_title="Severity Prediction", page_icon="🚑", layout="wide")
st.title("🚑 Collision severity prediction & model monitoring")


def api_get(path: str):
    try:
        r = requests.get(f"{API_URL}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        st.error(f"API not reachable at {API_URL}{path}: {exc}")
        return None


tab_predict, tab_model, tab_monitor = st.tabs(["Predict", "Model card", "Monitoring"])

# ------------------------------------------------------------------ predict
with tab_predict:
    with st.form("collision"):
        c1, c2, c3, c4 = st.columns(4)
        hour = c1.slider("Hour", 0, 23, 17)
        month = c1.slider("Month", 1, 12, 11)
        weekday = c1.selectbox("Weekday", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
                                           "Sunday"], index=4)
        latitude = c1.number_input("Latitude", 49.8, 61.0, 51.5074, format="%.4f")
        longitude = c1.number_input("Longitude", -8.7, 1.9, -0.1278, format="%.4f")

        nation = c2.selectbox("Nation", ["England", "Wales", "Scotland"])
        police_force = c2.text_input("Police force", "Metropolitan Police")
        urban = c2.selectbox("Urban / rural", ["Urban", "Rural"])
        road_class = c2.selectbox("Road class", ["A", "B", "C", "Motorway", "A(M)", "Unclassified"])
        road_type = c2.selectbox("Road type", ["Single carriageway", "Dual carriageway", "Roundabout",
                                               "One way street", "Slip road"])
        speed = c2.select_slider("Speed limit (mph)", [20, 30, 40, 50, 60, 70], 30)

        junction = c3.selectbox("Junction", ["Not at junction", "T or staggered junction", "Crossroads", "Roundabout",
                                             "Mini-roundabout", "Private drive or entrance", "Other junction"])
        junction_control = c3.selectbox("Junction control", ["Give way or uncontrolled", "Auto traffic signal",
                                                             "Not at junction", "Stop sign", "Authorised person"])
        light = c3.selectbox("Light", ["Daylight", "Darkness - lights lit", "Darkness - no lighting",
                                       "Darkness - lights unlit"])
        weather = c3.selectbox("Weather (reported)", ["Fine no high winds", "Raining no high winds",
                                                      "Fine + high winds", "Raining + high winds", "Fog or mist",
                                                      "Snowing no high winds"])
        surface = c3.selectbox("Road surface", ["Dry", "Wet or damp", "Frost or ice", "Snow"])

        vehicles = c4.number_input("Vehicles", 1, 20, 2)
        casualties = c4.number_input("Casualties", 1, 20, 1)
        temp = c4.number_input("Temperature (C)", -20.0, 40.0, 8.0)
        precip = c4.number_input("Precipitation (mm/h)", 0.0, 50.0, 0.0)
        wind = c4.number_input("Wind speed (km/h)", 0.0, 150.0, 15.0)
        youngest = c4.number_input("Youngest driver age", 16, 100, 30)
        flags = st.multiselect("Involved", ["pedestrian", "pedal cycle", "motorcycle", "car", "bus", "goods vehicle"],
                               default=["car"])
        submitted = st.form_submit_button("Predict severity", type="primary")

    if submitted:
        payload = {
            "hour": hour, "month": month, "weekday": weekday, "latitude": latitude, "longitude": longitude,
            "police_force": police_force, "nation": nation, "urban_or_rural": urban, "first_road_class": road_class,
            "road_type": road_type, "speed_limit": speed, "junction_detail": junction,
            "junction_control": junction_control, "light_conditions": light, "weather_conditions": weather,
            "road_surface_conditions": surface, "number_of_vehicles": vehicles, "number_of_casualties": casualties,
            "temperature_c": temp, "precipitation_mm": precip, "wind_speed_kmh": wind,
            "youngest_driver_age": youngest, "mean_driver_age": youngest,
            "pedestrian_involved": "pedestrian" in flags, "involves_pedal_cycle": "pedal cycle" in flags,
            "involves_motorcycle": "motorcycle" in flags, "involves_car": "car" in flags,
            "involves_bus": "bus" in flags, "involves_goods_vehicle": "goods vehicle" in flags,
        }
        try:
            r = requests.post(f"{API_URL}/predict", json=payload, timeout=10)
            r.raise_for_status()
            result = r.json()
            c1, c2 = st.columns([1, 2])
            c1.metric("Predicted severity", result["predicted_severity"])
            c1.metric("KSI probability", f"{result['ksi_probability']:.1%}")
            c1.caption(f"model v{result['model_version']} · {result['latency_ms']} ms")
            probs = pd.DataFrame({"severity": list(result["probabilities"]),
                                  "probability": list(result["probabilities"].values())})
            c2.plotly_chart(px.bar(probs, x="severity", y="probability", color="severity",
                                   color_discrete_map=COLORS, range_y=[0, 1]), width="stretch")
            st.caption("The model is trained with class weighting, so probabilities are calibrated towards "
                       "catching serious collisions rather than matching raw base rates.")
        except Exception as exc:
            st.error(f"Prediction failed: {exc}")

# ------------------------------------------------------------------ model card
with tab_model:
    meta_path = CHAMPION_DIR / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        m = meta["metrics"]
        st.subheader(f"{meta['model_name']} v{meta['version']} - {meta['model_family']} ({meta['class_weighting']})")
        st.caption(f"Trained {meta['trained_at']} · train window {meta['train_window'][0][:10]} → "
                   f"{meta['train_window'][1][:10]} · test window {meta['test_window'][0][:10]} → "
                   f"{meta['test_window'][1][:10]} · {meta['promotion_decision']}")
        cols = st.columns(5)
        cols[0].metric("Macro-F1", f"{m['test_macro_f1']:.3f}")
        cols[1].metric("Balanced accuracy", f"{m['test_balanced_accuracy']:.3f}")
        cols[2].metric("KSI recall", f"{m['test_ksi_recall']:.3f}")
        cols[3].metric("Recall - Fatal", f"{m['test_recall_fatal']:.3f}")
        cols[4].metric("Recall - Serious", f"{m['test_recall_serious']:.3f}")
        st.dataframe(pd.DataFrame([{k.replace("test_", ""): v for k, v in m.items()}]).T.rename(columns={0: "test"}),
                     width="stretch")
    else:
        st.info("No champion exported yet - run `python -m severity_model.train`.")
    info = api_get("/model-info")
    if info:
        st.caption(f"API is serving version {info.get('version')}")

# ------------------------------------------------------------------ monitoring
with tab_monitor:
    live = api_get("/metrics")
    if live:
        c = st.columns(4)
        c[0].metric("API requests", live["requests"])
        c[1].metric("Error rate", f"{live['error_rate']:.2%}")
        c[2].metric("Latency p95 (ms)", live["latency_ms"]["p95"] or "-")
        c[3].metric("Predicted classes", ", ".join(f"{k}: {v}" for k, v in live["predicted_class_counts"].items())
                    or "-")
    reports = sorted(REPORTS_DIR.glob("monitoring_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        st.info("No monitoring reports yet - run `python -m severity_model.monitoring`.")
    else:
        chosen = st.selectbox("Report", reports, format_func=lambda p: p.name)
        rep = json.loads(chosen.read_text(encoding="utf-8"))
        decision = rep["retraining"]
        (st.error if decision["required"] else st.success)(
            "RETRAINING REQUIRED" if decision["required"] else "No retraining needed")
        for reason in decision["reasons"]:
            st.write("•", reason)
        for warning in decision["warnings"]:
            st.warning(warning)

        drift = pd.DataFrame(rep["feature_drift"])
        st.plotly_chart(px.bar(drift.head(20), x="psi", y="feature", orientation="h", color="status",
                               color_discrete_map={"stable": "#4daf4a", "moderate": "#ff7f00",
                                                   "significant": "#e41a1c"},
                               title="Feature drift (PSI vs. training reference)"), width="stretch")
        c1, c2 = st.columns(2)
        cd = rep["class_drift"]
        rows = [{"distribution": "reference (pred)", **cd["reference_prediction_distribution"]},
                {"distribution": "current (pred)", **cd["prediction_distribution"]}]
        if "actual_distribution" in cd:
            rows += [{"distribution": "reference (actual)", **cd["reference_actual_distribution"]},
                     {"distribution": "current (actual)", **cd["actual_distribution"]}]
        long = pd.DataFrame(rows).melt(id_vars="distribution", var_name="severity", value_name="share")
        c1.plotly_chart(px.bar(long, x="distribution", y="share", color="severity", color_discrete_map=COLORS,
                               title="Class drift"), width="stretch")
        c2.subheader("Location drift")
        c2.json(rep["location_drift"])
        if "performance" in rep:
            p = rep["performance"]
            c2.subheader("Performance on labelled batch")
            c2.write(f"macro-F1 **{p['macro_f1']:.3f}** (baseline {p['baseline_macro_f1']:.3f}) · "
                     f"KSI false-negative rate **{p['ksi_false_negative_rate']:.3f}** "
                     f"(baseline {p['baseline_ksi_false_negative_rate']:.3f})")
        st.subheader("Input data quality")
        st.dataframe(pd.DataFrame(rep["data_quality"]["features"]), width="stretch", hide_index=True)

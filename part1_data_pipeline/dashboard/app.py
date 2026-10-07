"""Streamlit dashboard for the traffic accident warehouse.

Run:  streamlit run dashboard/app.py
Reads the warehouse configured by DATABASE_URL (PostgreSQL or the local
SQLite fallback). All charts are computed from the star schema / mart tables.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from traffic_pipeline.config import get_settings  # noqa: E402

st.set_page_config(page_title="UK Road Collision Severity", page_icon="🚦", layout="wide")

SEVERITY_COLORS = {"Fatal": "#b2182b", "Serious": "#ef8a62", "Slight": "#67a9cf"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

ACCIDENT_SQL = """
SELECT f.collision_index, f.latitude, f.longitude, f.number_of_casualties, f.number_of_vehicles,
       f.temperature_c, f.precipitation_mm, f.wind_speed_kmh, f.weather_matched,
       d.full_date, d.year, d.month, d.weekday_name, d.weekday_num, d.is_weekend, d.season,
       t.hour_key AS hour, t.time_band,
       l.police_force_name, l.nation, l.urban_rural_label,
       r.first_road_class_label, r.road_type_label, r.speed_limit_label, r.junction_detail_label,
       w.weather_conditions_label, w.road_surface_label, w.light_conditions_label,
       w.temperature_band, w.precipitation_band, w.wind_band,
       s.severity_label, s.is_ksi
FROM fact_accident f
JOIN dim_date d ON f.date_key = d.date_key
JOIN dim_time t ON f.hour_key = t.hour_key
JOIN dim_location l ON f.location_key = l.location_key
JOIN dim_road r ON f.road_key = r.road_key
JOIN dim_weather w ON f.weather_key = w.weather_key
JOIN dim_severity s ON f.severity_key = s.severity_key
"""


@st.cache_resource
def engine():
    return create_engine(get_settings().database_url)


@st.cache_data(ttl=600, show_spinner="Loading accidents from the warehouse ...")
def load_accidents() -> pd.DataFrame:
    df = pd.read_sql(ACCIDENT_SQL, engine())
    df["is_ksi"] = df["is_ksi"].astype(bool)
    return df


@st.cache_data(ttl=600)
def load_table(name: str, limit: int | None = None) -> pd.DataFrame:
    sql = f"SELECT * FROM {name}" + (f" LIMIT {limit}" if limit else "")
    return pd.read_sql(sql, engine())


@st.cache_data(ttl=600)
def load_vehicle_casualty() -> pd.DataFrame:
    sql = """
    SELECT c.casualty_severity, c.casualty_class, c.age_band_of_casualty, c.sex_of_casualty,
           COALESCE(v.vehicle_category, 'Unknown') AS vehicle_category, d.year, l.nation, l.urban_rural_label
    FROM fact_casualty c
    JOIN fact_accident f ON c.collision_index = f.collision_index
    JOIN dim_date d ON c.date_key = d.date_key
    JOIN dim_location l ON f.location_key = l.location_key
    LEFT JOIN fact_vehicle v ON c.collision_index = v.collision_index AND c.vehicle_reference = v.vehicle_reference
    """
    return pd.read_sql(sql, engine())


def ksi_summary(df: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    out = df.groupby(by).agg(accidents=("collision_index", "size"), ksi=("is_ksi", "sum")).reset_index()
    out["ksi_rate_pct"] = (100 * out["ksi"] / out["accidents"]).round(2)
    return out


# ------------------------------------------------------------------ guard
if "fact_accident" not in inspect(engine()).get_table_names():
    st.error("The warehouse is empty. Run the pipeline first: `python -m traffic_pipeline.cli run`")
    st.stop()

acc = load_accidents()

# ------------------------------------------------------------------ sidebar filters
st.sidebar.header("Filters")
years = sorted(acc["year"].unique())
sel_years = st.sidebar.multiselect("Year", years, default=years)
nations = sorted(acc["nation"].unique())
sel_nations = st.sidebar.multiselect("Nation", nations, default=nations)
areas = sorted(acc["urban_rural_label"].unique())
sel_areas = st.sidebar.multiselect("Urban / rural", areas, default=areas)
forces = ["All"] + sorted(acc["police_force_name"].unique())
sel_force = st.sidebar.selectbox("Police force", forces)
sel_sev = st.sidebar.multiselect("Severity", ["Fatal", "Serious", "Slight"], default=["Fatal", "Serious", "Slight"])

mask = (acc["year"].isin(sel_years) & acc["nation"].isin(sel_nations)
        & acc["urban_rural_label"].isin(sel_areas) & acc["severity_label"].isin(sel_sev))
if sel_force != "All":
    mask &= acc["police_force_name"] == sel_force
df = acc[mask]

st.sidebar.caption(f"Run id: `{(get_settings().analytics_dir / 'latest' / 'RUN_ID').read_text().strip()}`"
                   if (get_settings().analytics_dir / "latest" / "RUN_ID").exists() else "")

st.title("🚦 UK Road Collision Severity Analytics")
st.caption("Source: DfT STATS19 Road Safety Open Data + Open-Meteo historical weather. "
           "KSI = killed or seriously injured.")

if df.empty:
    st.warning("No collisions match the selected filters.")
    st.stop()

# ------------------------------------------------------------------ KPIs
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Collisions", f"{len(df):,}")
k2.metric("Fatal", f"{(df.severity_label == 'Fatal').sum():,}")
k3.metric("Serious", f"{(df.severity_label == 'Serious').sum():,}")
k4.metric("KSI rate", f"{df.is_ksi.mean():.1%}")
k5.metric("Casualties", f"{int(df.number_of_casualties.sum()):,}")
k6.metric("Weather matched", f"{df.weather_matched.astype(bool).mean():.1%}")

tabs = st.tabs(["Severity", "Time patterns", "Weather & road", "Hotspot map", "Vehicles & casualties",
                "Pipeline & data quality"])

# 1 ---------------------------------------------------------------- severity distribution
with tabs[0]:
    c1, c2 = st.columns(2)
    sev = df["severity_label"].value_counts().reindex(["Fatal", "Serious", "Slight"]).dropna().reset_index()
    sev.columns = ["severity", "collisions"]
    sev["share_pct"] = (100 * sev["collisions"] / sev["collisions"].sum()).round(2)
    c1.plotly_chart(px.bar(sev, x="severity", y="collisions", color="severity", text="share_pct",
                           color_discrete_map=SEVERITY_COLORS, title="Collisions by severity (% labels)"),
                    width="stretch")
    monthly = df.groupby([pd.to_datetime(df["full_date"]).dt.to_period("M").dt.to_timestamp(), "severity_label"]) \
        .size().rename("collisions").reset_index().rename(columns={"full_date": "month"})
    c2.plotly_chart(px.area(monthly, x="month", y="collisions", color="severity_label",
                            color_discrete_map=SEVERITY_COLORS, title="Monthly collisions by severity"),
                    width="stretch")
    st.info("Severity is highly imbalanced: slight collisions dominate, which is why Part 2 uses class "
            "weighting and tracks macro-F1 / recall rather than accuracy.")

# 2 ---------------------------------------------------------------- hour x weekday
with tabs[1]:
    heat = df.groupby(["weekday_name", "hour"]).size().rename("collisions").reset_index()
    heat = heat.pivot(index="weekday_name", columns="hour", values="collisions").reindex(WEEKDAYS)
    st.plotly_chart(px.imshow(heat, aspect="auto", color_continuous_scale="YlOrRd",
                              labels=dict(x="Hour of day", y="", color="Collisions"),
                              title="Collisions by hour and weekday"), width="stretch")
    c1, c2 = st.columns(2)
    hourly = ksi_summary(df, "hour")
    c1.plotly_chart(px.line(hourly, x="hour", y="ksi_rate_pct", markers=True,
                            title="KSI rate (%) by hour - night-time collisions are more severe"),
                    width="stretch")
    by_day = ksi_summary(df, "weekday_name").set_index("weekday_name").reindex(WEEKDAYS).reset_index()
    c2.plotly_chart(px.bar(by_day, x="weekday_name", y="accidents", color="ksi_rate_pct",
                           color_continuous_scale="Reds", title="Collisions and KSI rate by weekday"),
                    width="stretch")

# 3 ---------------------------------------------------------------- weather / road conditions
with tabs[2]:
    factor_map = {
        "Police-recorded weather": "weather_conditions_label", "Road surface": "road_surface_label",
        "Light conditions": "light_conditions_label", "Measured precipitation": "precipitation_band",
        "Measured temperature": "temperature_band", "Measured wind": "wind_band",
        "Speed limit": "speed_limit_label", "Road type": "road_type_label",
        "Road class": "first_road_class_label", "Junction": "junction_detail_label",
    }
    choice = st.selectbox("Contributing factor", list(factor_map), index=1)
    col = factor_map[choice]
    impact = ksi_summary(df, col).sort_values("accidents", ascending=False)
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(impact, x=col, y="accidents", title=f"Collisions by {choice.lower()}"),
                    width="stretch")
    c2.plotly_chart(px.bar(impact[impact["accidents"] >= 30], x=col, y="ksi_rate_pct", color="ksi_rate_pct",
                           color_continuous_scale="Reds",
                           title=f"KSI rate (%) by {choice.lower()} (levels with 30+ collisions)"),
                    width="stretch")
    speed = ksi_summary(df[df["speed_limit_label"] != "Unknown"], ["speed_limit_label", "urban_rural_label"])
    speed["speed"] = pd.to_numeric(speed["speed_limit_label"], errors="coerce")
    st.plotly_chart(px.line(speed.sort_values("speed"), x="speed", y="ksi_rate_pct", color="urban_rural_label",
                            markers=True, title="KSI rate (%) by speed limit (mph) and area"),
                    width="stretch")

# 4 ---------------------------------------------------------------- hotspot map
with tabs[3]:
    grid = st.slider("Hotspot grid size (degrees)", 0.01, 0.2, 0.05, 0.01)
    h = df.assign(cell_lat=(df.latitude / grid).round() * grid, cell_lon=(df.longitude / grid).round() * grid)
    hot = h.groupby(["cell_lat", "cell_lon"]).agg(collisions=("collision_index", "size"),
                                                 ksi=("is_ksi", "sum")).reset_index()
    hot["ksi_rate_pct"] = (100 * hot["ksi"] / hot["collisions"]).round(1)
    min_n = st.slider("Minimum collisions per cell", 1, 200, 10)
    hot = hot[hot["collisions"] >= min_n]
    fig = px.scatter_map(hot, lat="cell_lat", lon="cell_lon", size="collisions", color="ksi_rate_pct",
                         color_continuous_scale="YlOrRd", size_max=25, zoom=4.6,
                         center={"lat": 54.0, "lon": -2.5}, map_style="carto-positron", height=650,
                         hover_data={"collisions": True, "ksi": True, "ksi_rate_pct": True},
                         title="Collision hotspots (size = collisions, colour = KSI rate %)")
    st.plotly_chart(fig, width="stretch")
    top = hot.sort_values("collisions", ascending=False).head(15)
    st.dataframe(top, width="stretch", hide_index=True)

# 5 ---------------------------------------------------------------- vehicles & casualties
with tabs[4]:
    vc = load_vehicle_casualty()
    vc = vc[vc["year"].isin(sel_years) & vc["nation"].isin(sel_nations) & vc["urban_rural_label"].isin(sel_areas)]
    c1, c2 = st.columns(2)
    by_vehicle = vc.groupby(["vehicle_category", "casualty_severity"]).size().rename("casualties").reset_index()
    c1.plotly_chart(px.bar(by_vehicle, x="vehicle_category", y="casualties", color="casualty_severity",
                           color_discrete_map=SEVERITY_COLORS, title="Casualties by vehicle category"),
                    width="stretch")
    share = (vc.assign(ksi=vc["casualty_severity"].isin(["Fatal", "Serious"]))
             .groupby("casualty_class")["ksi"].mean().mul(100).round(1).rename("ksi_pct").reset_index())
    c2.plotly_chart(px.bar(share, x="casualty_class", y="ksi_pct",
                           title="Share of casualties killed or seriously injured (%) by road-user class"),
                    width="stretch")
    ages = vc[vc["age_band_of_casualty"] != "Unknown"].groupby(["age_band_of_casualty", "casualty_severity"]) \
        .size().rename("casualties").reset_index()
    order = ["0-5", "6-10", "11-15", "16-20", "21-25", "26-35", "36-45", "46-55", "56-65", "66-75", "Over 75"]
    st.plotly_chart(px.bar(ages, x="age_band_of_casualty", y="casualties", color="casualty_severity",
                           category_orders={"age_band_of_casualty": order}, color_discrete_map=SEVERITY_COLORS,
                           title="Casualties by age band"), width="stretch")

# 6 ---------------------------------------------------------------- pipeline / DQ
with tabs[5]:
    st.subheader("Latest pipeline steps")
    runs = load_table("etl_run_log")
    # run ids are free text (e.g. manual "--run-id"), so pick the latest by start time
    last = runs.sort_values("started_at_utc")["run_id"].iloc[-1] if not runs.empty else None
    if last:
        st.dataframe(runs[runs["run_id"] == last], width="stretch", hide_index=True)
    st.subheader("Ingestion log (latest run)")
    ing = load_table("etl_ingestion_log")
    if not ing.empty:
        latest = ing[ing["run_id"] == last]
        st.write(latest.groupby(["source", "status"]).size().rename("files/requests").reset_index())
        st.dataframe(latest[["source", "dataset", "status", "row_count", "bytes", "extracted_at_utc", "message"]],
                     width="stretch", hide_index=True)
    st.subheader("Data-quality rule hits (latest run)")
    rej = load_table("dq_rejected_records")
    rej = rej[rej["run_id"] == last]
    if not rej.empty:
        summary = rej.groupby(["table_name", "rule_id", "action", "description"]).size() \
            .rename("records").reset_index()
        st.dataframe(summary, width="stretch", hide_index=True)
        st.caption("Sample of rejected records")
        st.dataframe(rej.head(200), width="stretch", hide_index=True)
    else:
        st.success("No records were rejected in the latest run.")

import pandas as pd

from traffic_pipeline import lookups, transform
from traffic_pipeline.extract import assign_weather_cell


def test_unknown_codes_get_a_traceable_label():
    labels = lookups.label(pd.Series([1, 2, 42, None]), lookups.SEVERITY)
    assert list(labels) == ["Fatal", "Serious", "Unknown (code 42)", "Unknown"]


def test_police_force_maps_to_nation():
    assert list(lookups.nation(pd.Series([1, 62, 97]))) == ["England", "Wales", "Scotland"]


def test_weather_cell_snaps_to_grid():
    df = assign_weather_cell(pd.DataFrame({"latitude": [51.74], "longitude": [-0.26]}), 0.5)
    assert df["weather_cell_id"].iat[0] == "51.50_-0.50"


def test_weather_join_matches_on_cell_and_hour():
    collisions = pd.DataFrame({
        "latitude": [51.5, 53.0], "longitude": [-0.1, -2.2],
        "weather_join_time": pd.to_datetime(["2023-05-01 08:00", "2023-05-01 09:00"]),
    })
    weather = pd.DataFrame({
        "weather_cell_id": ["51.50_0.00"], "weather_time": pd.to_datetime(["2023-05-01 08:00"]),
        "temperature_2m": [12.0], "precipitation": [0.0], "rain": [0.0], "snowfall": [0.0],
        "wind_speed_10m": [15.0], "wind_gusts_10m": [25.0], "cloud_cover": [50.0],
        "relative_humidity_2m": [70.0], "weather_code": [3.0],
    })
    out = transform.join_weather(collisions, weather, 0.5)
    assert list(out["weather_matched"]) == [True, False]
    assert out["temperature_band"].iat[0] == "10-15C"
    assert out["precipitation_band"].iat[1] == "Unknown"


def test_bands_cover_edges():
    assert list(transform.precipitation_band(pd.Series([0.0, 0.3, 1.0, 5.0]))) == [
        "Dry (0 mm/h)", "Light (<0.5 mm/h)", "Moderate (0.5-2 mm/h)", "Heavy (>2 mm/h)"]
    assert list(transform.time_band(pd.Series([0, 7, 12, 17, 23]))) == [
        "Night (00-05)", "Morning peak (06-09)", "Daytime (10-15)", "Evening peak (16-19)", "Late evening (20-23)"]


def test_surrogate_keys_are_stable_and_complete():
    df = pd.DataFrame({"a": ["x", "y", "x", None], "b": ["1", "1", "1", "2"]})
    dim, keys = transform._surrogate_key(df, ["a", "b"], "k")
    assert len(dim) == 3
    assert keys.iat[0] == keys.iat[2]
    assert keys.notna().all()


def test_dim_date_is_continuous():
    dim = transform.build_dim_date(pd.Series(pd.to_datetime(["2023-12-30", "2024-01-02"])))
    assert list(dim["date_key"]) == [20231230, 20231231, 20240101, 20240102]
    assert dim.loc[dim["date_key"] == 20231231, "weekday_name"].iat[0] == "Sunday"

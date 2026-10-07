import pandas as pd
import pytest

from traffic_pipeline import quality


def staged_collisions() -> pd.DataFrame:
    rows = [
        # id,    date,          hour, sev, lat,   lon,  veh, cas, speed
        ("A1", "2023-03-01", 8, 3, 51.5, -0.1, 2, 1, 30),     # valid
        ("A1", "2023-03-01", 8, 3, 51.5, -0.1, 2, 1, 30),     # duplicate -> DQ002
        (None, "2023-03-01", 8, 3, 51.5, -0.1, 2, 1, 30),     # missing id -> DQ001
        ("A3", None, 8, 3, 51.5, -0.1, 2, 1, 30),             # bad date -> DQ003
        ("A4", "2019-01-01", 8, 3, 51.5, -0.1, 2, 1, 30),     # outside years -> DQ004
        ("A5", "2023-03-01", None, 3, 51.5, -0.1, 2, 1, 30),  # bad time -> DQ005
        ("A6", "2023-03-01", 8, 7, 51.5, -0.1, 2, 1, 30),     # bad severity -> DQ006
        ("A7", "2023-03-01", 8, 2, None, -0.1, 2, 1, 30),     # missing coords -> DQ007
        ("A8", "2023-03-01", 8, 2, 40.0, -0.1, 2, 1, 30),     # outside UK -> DQ008
        ("A9", "2023-03-01", 8, 1, 52.0, -1.0, 0, 1, 30),     # 0 vehicles -> DQ009
        ("B1", "2023-03-01", 8, 1, 52.0, -1.0, 1, None, 30),  # missing casualties -> DQ010
        ("B2", "2023-03-01", 8, 1, 52.0, -1.0, 1, 1, 33),     # bad speed -> nullified, kept
    ]
    df = pd.DataFrame(rows, columns=["collision_index", "collision_date", "collision_hour", "collision_severity",
                                     "latitude", "longitude", "number_of_vehicles", "number_of_casualties",
                                     "speed_limit"])
    df["collision_index"] = df["collision_index"].astype("string")
    df["collision_date"] = pd.to_datetime(df["collision_date"])
    for col in ["collision_hour", "collision_severity", "number_of_vehicles", "number_of_casualties", "speed_limit"]:
        df[col] = df[col].astype("Int64")
    df["_source_file"] = "test.csv"
    return df


@pytest.fixture(autouse=True)
def years(monkeypatch, tmp_path):
    monkeypatch.setenv("STATS19_YEARS", "2023,2024")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_collision_rules_reject_and_log_each_bad_row():
    log = quality.QualityLog("t")
    clean = quality.clean_collisions(staged_collisions(), log)
    assert list(clean["collision_index"]) == ["A1", "B2"]
    hits = log.frame().groupby("rule_id").size().to_dict()
    for rule in ["DQ001", "DQ002", "DQ003", "DQ004", "DQ005", "DQ006", "DQ007", "DQ008", "DQ009", "DQ010",
                 "DQ011"]:
        assert hits.get(rule) == 1, rule
    assert pd.isna(clean.loc[clean["collision_index"] == "B2", "speed_limit"]).all()


def test_orphan_and_duplicate_vehicles_are_rejected():
    vehicles = pd.DataFrame({
        "collision_index": pd.Series(["A1", "A1", "ZZ"], dtype="string"),
        "vehicle_reference": pd.Series([1, 1, 1], dtype="Int64"),
        "age_of_driver": pd.Series([30, 30, 200], dtype="Int64"),
        "_source_file": "v.csv",
    })
    log = quality.QualityLog("t")
    clean = quality.clean_vehicles(vehicles, pd.Series(["A1"]), log)
    assert len(clean) == 1
    assert set(log.frame()["rule_id"]) == {"DQ101", "DQ102"}


def test_minus_one_age_is_missing_not_an_error():
    casualties = pd.DataFrame({
        "collision_index": pd.Series(["A1", "A1"], dtype="string"),
        "casualty_reference": pd.Series([1, 2], dtype="Int64"),
        "casualty_severity": pd.Series([3, 2], dtype="Int64"),
        "age_of_casualty": pd.Series([-1, 150], dtype="Int64"),
        "_source_file": "c.csv",
    })
    log = quality.QualityLog("t")
    clean = quality.clean_casualties(casualties, pd.Series(["A1"]), log)
    assert clean["age_of_casualty"].isna().all()
    assert list(log.frame()["rule_id"]) == ["DQ204"]  # only the 150 is logged


def test_weather_out_of_range_values_are_nullified():
    weather = pd.DataFrame({
        "weather_cell_id": ["51.50_-0.00"] * 2,
        "weather_time": pd.to_datetime(["2023-01-01 00:00", "2023-01-01 01:00"]),
        "temperature_2m": [5.0, 99.0], "precipitation": [0.1, -3.0],
        "wind_speed_10m": [10.0, 10.0], "relative_humidity_2m": [80.0, 80.0],
    })
    log = quality.QualityLog("t")
    clean = quality.clean_weather(weather, log)
    assert clean["temperature_2m"].isna().sum() == 1
    assert clean["precipitation"].isna().sum() == 1
    assert len(clean) == 2

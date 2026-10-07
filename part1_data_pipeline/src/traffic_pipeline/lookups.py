"""Code -> label lookups for coded STATS19 fields.

Labels follow the DfT "Road Safety Open Data - data guide". Codes that are not
listed here are mapped to "Unknown (code N)" instead of failing, so a new code
introduced by DfT never breaks the pipeline; it simply shows up in the
dashboard and can then be added here.
"""
from __future__ import annotations

import pandas as pd

SEVERITY = {1: "Fatal", 2: "Serious", 3: "Slight"}

DAY_OF_WEEK = {1: "Sunday", 2: "Monday", 3: "Tuesday", 4: "Wednesday", 5: "Thursday", 6: "Friday", 7: "Saturday"}

FIRST_ROAD_CLASS = {1: "Motorway", 2: "A(M)", 3: "A", 4: "B", 5: "C", 6: "Unclassified", -1: "Unknown", 9: "Unknown"}

ROAD_TYPE = {
    1: "Roundabout", 2: "One way street", 3: "Dual carriageway", 6: "Single carriageway",
    7: "Slip road", 9: "Unknown", 12: "One way street/Slip road", -1: "Unknown",
}

JUNCTION_DETAIL = {
    0: "Not at junction", 1: "Roundabout", 2: "Mini-roundabout", 3: "T or staggered junction",
    5: "Slip road", 6: "Crossroads", 7: "More than 4 arms", 8: "Private drive or entrance",
    9: "Other junction", 13: "Junction - unknown type", 99: "Unknown", -1: "Unknown",
}

JUNCTION_CONTROL = {
    0: "Not at junction", 1: "Authorised person", 2: "Auto traffic signal", 3: "Stop sign",
    4: "Give way or uncontrolled", 9: "Unknown", -1: "Unknown",
}

LIGHT_CONDITIONS = {
    1: "Daylight", 4: "Darkness - lights lit", 5: "Darkness - lights unlit",
    6: "Darkness - no lighting", 7: "Darkness - lighting unknown", -1: "Unknown",
}

WEATHER_CONDITIONS = {
    1: "Fine no high winds", 2: "Raining no high winds", 3: "Snowing no high winds",
    4: "Fine + high winds", 5: "Raining + high winds", 6: "Snowing + high winds",
    7: "Fog or mist", 8: "Other", 9: "Unknown", -1: "Unknown",
}

ROAD_SURFACE = {
    1: "Dry", 2: "Wet or damp", 3: "Snow", 4: "Frost or ice", 5: "Flood over 3cm deep",
    6: "Oil or diesel", 7: "Mud", 9: "Unknown", -1: "Unknown",
}

SPECIAL_CONDITIONS = {
    0: "None", 1: "Traffic signal out", 2: "Traffic signal defective", 3: "Signs defective or obscured",
    4: "Roadworks", 5: "Road surface defective", 6: "Oil or diesel", 7: "Mud", 9: "Unknown", -1: "Unknown",
}

CARRIAGEWAY_HAZARDS = {
    0: "None", 1: "Vehicle load on road", 2: "Other object on road", 3: "Previous accident",
    4: "Dog on road", 5: "Other animal on road", 6: "Pedestrian in carriageway", 7: "Animal on road",
    9: "Unknown", -1: "Unknown",
}

URBAN_RURAL = {1: "Urban", 2: "Rural", 3: "Unallocated", -1: "Unknown"}

POLICE_ATTENDED = {1: "Yes", 2: "No", 3: "No - self reported", -1: "Unknown"}

SEX = {1: "Male", 2: "Female", 3: "Not known", 9: "Unknown", -1: "Unknown"}

CASUALTY_CLASS = {1: "Driver or rider", 2: "Passenger", 3: "Pedestrian"}

AGE_BAND = {
    1: "0-5", 2: "6-10", 3: "11-15", 4: "16-20", 5: "21-25", 6: "26-35", 7: "36-45",
    8: "46-55", 9: "56-65", 10: "66-75", 11: "Over 75", -1: "Unknown",
}

VEHICLE_TYPE = {
    1: "Pedal cycle", 2: "Motorcycle 50cc and under", 3: "Motorcycle 125cc and under",
    4: "Motorcycle 125-500cc", 5: "Motorcycle over 500cc", 8: "Taxi/Private hire car", 9: "Car",
    10: "Minibus (8-16 seats)", 11: "Bus or coach (17+ seats)", 16: "Ridden horse",
    17: "Agricultural vehicle", 18: "Tram", 19: "Van / Goods 3.5t or under",
    20: "Goods 3.5t-7.5t", 21: "Goods 7.5t and over", 22: "Mobility scooter",
    23: "Electric motorcycle", 90: "Other vehicle", 97: "Motorcycle - unknown cc",
    98: "Goods vehicle - unknown weight", 99: "Unknown", -1: "Unknown",
}

VEHICLE_CATEGORY = {
    1: "Pedal cycle", 2: "Motorcycle", 3: "Motorcycle", 4: "Motorcycle", 5: "Motorcycle",
    23: "Motorcycle", 97: "Motorcycle", 8: "Car", 9: "Car", 10: "Bus", 11: "Bus",
    19: "Goods vehicle", 20: "Goods vehicle", 21: "Goods vehicle", 98: "Goods vehicle",
    16: "Other", 17: "Other", 18: "Other", 22: "Other", 90: "Other",
}

# Police force codes -> (name, nation). Used for the location dimension and
# for location-drift monitoring in Part 2.
POLICE_FORCE = {
    1: ("Metropolitan Police", "England"), 3: ("Cumbria", "England"), 4: ("Lancashire", "England"),
    5: ("Merseyside", "England"), 6: ("Greater Manchester", "England"), 7: ("Cheshire", "England"),
    10: ("Northumbria", "England"), 11: ("Durham", "England"), 12: ("North Yorkshire", "England"),
    13: ("West Yorkshire", "England"), 14: ("South Yorkshire", "England"), 16: ("Humberside", "England"),
    17: ("Cleveland", "England"), 20: ("West Midlands", "England"), 21: ("Staffordshire", "England"),
    22: ("West Mercia", "England"), 23: ("Warwickshire", "England"), 30: ("Derbyshire", "England"),
    31: ("Nottinghamshire", "England"), 32: ("Lincolnshire", "England"), 33: ("Leicestershire", "England"),
    34: ("Northamptonshire", "England"), 35: ("Cambridgeshire", "England"), 36: ("Norfolk", "England"),
    37: ("Suffolk", "England"), 40: ("Bedfordshire", "England"), 41: ("Hertfordshire", "England"),
    42: ("Essex", "England"), 43: ("Thames Valley", "England"), 44: ("Hampshire", "England"),
    45: ("Surrey", "England"), 46: ("Kent", "England"), 47: ("Sussex", "England"),
    48: ("City of London", "England"), 50: ("Devon and Cornwall", "England"),
    52: ("Avon and Somerset", "England"), 53: ("Gloucestershire", "England"), 54: ("Wiltshire", "England"),
    55: ("Dorset", "England"), 60: ("North Wales", "Wales"), 61: ("Gwent", "Wales"),
    62: ("South Wales", "Wales"), 63: ("Dyfed-Powys", "Wales"), 91: ("Northern", "Scotland"),
    92: ("Grampian", "Scotland"), 93: ("Tayside", "Scotland"), 94: ("Fife", "Scotland"),
    95: ("Lothian and Borders", "Scotland"), 96: ("Central", "Scotland"), 97: ("Strathclyde", "Scotland"),
    98: ("Dumfries and Galloway", "Scotland"), 99: ("Police Scotland", "Scotland"),
}


def label(series: pd.Series, mapping: dict, unknown: str = "Unknown") -> pd.Series:
    """Map integer codes to labels; unmapped codes become 'Unknown (code N)'."""
    codes = pd.to_numeric(series, errors="coerce")
    labels = codes.map(mapping)
    unmapped = labels.isna() & codes.notna()
    labels = labels.astype("object")
    labels[unmapped] = "Unknown (code " + codes[unmapped].astype("Int64").astype(str) + ")"
    return labels.fillna(unknown)


def police_force_name(series: pd.Series) -> pd.Series:
    return label(series, {k: v[0] for k, v in POLICE_FORCE.items()})


def nation(series: pd.Series) -> pd.Series:
    return label(series, {k: v[1] for k, v in POLICE_FORCE.items()})

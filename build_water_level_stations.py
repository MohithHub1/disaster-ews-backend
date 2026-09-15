import glob
import json
import os

import pandas as pd


OUTPUT_FILE = "water_level_stations.json"

CSV_FILES = [
    file
    for file in glob.glob("CWC_*.csv")
    if os.path.basename(file) != OUTPUT_FILE
]


def find_column(columns, names):
    """
    Find a column using exact names first, then
    case-insensitive matching.
    """
    for name in names:
        if name in columns:
            return name

    lower_columns = {
        str(column).strip().lower(): column
        for column in columns
    }

    for name in names:
        column = lower_columns.get(name.strip().lower())
        if column is not None:
            return column

    return None


all_stations = {}

for input_file in CSV_FILES:
    print(f"Reading: {input_file}")

    df = pd.read_csv(input_file)

    station_col = find_column(
        df.columns,
        ["Station", "Station Name"],
    )

    latitude_col = find_column(
        df.columns,
        ["Latitude", "latitude"],
    )

    longitude_col = find_column(
        df.columns,
        ["Longitude", "longitude"],
    )

    river_col = find_column(
        df.columns,
        ["River", "River Name", "Basin"],
    )

    state_col = find_column(
        df.columns,
        ["State"],
    )

    district_col = find_column(
        df.columns,
        ["District"],
    )

    village_col = find_column(
        df.columns,
        ["Village"],
    )

    time_col = find_column(
        df.columns,
        [
            "Data Acquisition Time",
            "Date",
            "Date Time",
            "Datetime",
        ],
    )

    water_level_col = find_column(
        df.columns,
        [
            "River Water Level Telemetry Hourly (meter)",
            "River Water Level",
            "Water Level",
        ],
    )

    required = {
        "station": station_col,
        "latitude": latitude_col,
        "longitude": longitude_col,
        "time": time_col,
        "water_level": water_level_col,
    }

    missing = [
        name
        for name, column in required.items()
        if column is None
    ]

    if missing:
        print(
            f"Skipping {input_file}. "
            f"Missing columns: {missing}"
        )
        continue

    df[time_col] = pd.to_datetime(
        df[time_col],
        dayfirst=True,
        errors="coerce",
    )

    df[water_level_col] = pd.to_numeric(
        df[water_level_col],
        errors="coerce",
    )

    df[latitude_col] = pd.to_numeric(
        df[latitude_col],
        errors="coerce",
    )

    df[longitude_col] = pd.to_numeric(
        df[longitude_col],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            station_col,
            latitude_col,
            longitude_col,
            time_col,
            water_level_col,
        ]
    )

    # Keep only the latest observation for each station.
    latest = (
        df.sort_values(time_col)
        .groupby(
            [
                station_col,
                latitude_col,
                longitude_col,
            ],
            as_index=False,
        )
        .tail(1)
    )

    for _, row in latest.iterrows():
        station_name = str(row[station_col]).strip()
        latitude = float(row[latitude_col])
        longitude = float(row[longitude_col])

        key = (
            f"{station_name}|"
            f"{latitude:.6f}|"
            f"{longitude:.6f}"
        )

        all_stations[key] = {
            "station_name": station_name,
            "latitude": latitude,
            "longitude": longitude,
            "river": (
                str(row[river_col])
                if river_col
                else ""
            ),
            "state": (
                str(row[state_col])
                if state_col
                else ""
            ),
            "district": (
                str(row[district_col])
                if district_col
                else ""
            ),
            "village": (
                str(row[village_col])
                if village_col
                else ""
            ),
            "water_level_m": float(
                row[water_level_col]
            ),
            "observed_at": row[time_col].isoformat(),
        }


stations = list(all_stations.values())

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8",
) as file:
    json.dump(
        stations,
        file,
        indent=2,
        ensure_ascii=False,
    )

print()
print(f"CSV files processed: {len(CSV_FILES)}")
print(f"Unique stations created: {len(stations)}")
print(f"Saved to: {OUTPUT_FILE}")
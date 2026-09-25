"""Combine raw session parquet into processed tables."""
from __future__ import annotations

import unicodedata

import pandas as pd

from f1pred import config

RACE_KEYS = ["Season", "RoundNumber"]
MIN_ENTRIES = 18
LAP_SESSIONS = ["FP1", "FP2", "FP3", "S"]
LAP_COLS = [
    "Season", "RoundNumber", "SessionCode", "Driver", "Team", "LapNumber", "Stint",
    "Compound", "TyreLife", "LapTimeSeconds", "PitInTimeSeconds", "PitOutTimeSeconds",
    "TrackStatus", "IsAccurate", "Deleted",
]


def _read(table: str) -> pd.DataFrame:
    files = sorted(config.RAW_DIR.glob(f"*/R*_{table}.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def normalize_location(name: str) -> str:
    key = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().strip().lower()
    return config.LOCATION_ALIASES.get(key, key)


def _lookup(entries: pd.DataFrame, keys: list[str], col: str) -> pd.Series:
    known = entries.dropna(subset=keys + [col]).sort_values(RACE_KEYS).drop_duplicates(keys, keep="last")
    return entries[keys].merge(known[keys + [col]], on=keys, how="left")[col].set_axis(entries.index)


def build_entries(results: pd.DataFrame) -> pd.DataFrame:
    event_cols = RACE_KEYS + ["EventName", "EventFormat", "Location"]
    driver_cols = ["DriverId", "Abbreviation", "TeamId", "TeamName"]

    # FastF1 stores missing Q identity as the string "nan" for drivers without a time.
    results = results.copy()
    results[driver_cols] = results[driver_cols].replace(["", "nan", "None"], pd.NA)
    identity = results.groupby(RACE_KEYS + ["DriverNumber"])[driver_cols]
    results[driver_cols] = identity.transform(lambda s: s.ffill().bfill())

    quali = results[results["SessionCode"] == "Q"]
    quali = quali[event_cols + driver_cols + ["Position", "Q1Seconds", "Q2Seconds", "Q3Seconds"]].rename(
        columns={"Position": "QPosition"})
    quali["QBestSeconds"] = quali[["Q1Seconds", "Q2Seconds", "Q3Seconds"]].min(axis=1)
    quali = quali.drop(columns=["Q1Seconds", "Q2Seconds", "Q3Seconds"])

    race = results[results["SessionCode"] == "R"]
    race = race[event_cols + driver_cols + [
        "GridPosition", "Position", "ClassifiedPosition", "Status", "Points", "Laps"]].rename(
        columns={"Position": "FinishPosition", "ClassifiedPosition": "Classified", "Laps": "RaceLaps"})

    sprint = results[results["SessionCode"] == "S"]
    sprint = sprint[RACE_KEYS + ["DriverId", "Position", "GridPosition"]].rename(
        columns={"Position": "SprintPosition", "GridPosition": "SprintGrid"})

    keys = RACE_KEYS + ["DriverId"]
    entries = quali.merge(race, on=keys, how="outer", suffixes=("", "_r"))
    for col in event_cols[2:] + driver_cols[1:]:
        entries[col] = entries[col].fillna(entries.pop(f"{col}_r"))
    # Quali results for an upcoming race can lack TeamId and DriverId; the names still identify them.
    entries["TeamId"] = entries["TeamId"].fillna(_lookup(entries, ["Season", "TeamName"], "TeamId"))
    entries["DriverId"] = entries["DriverId"].fillna(_lookup(entries, ["Season", "Abbreviation"], "DriverId"))
    entries["DriverId"] = entries["DriverId"].fillna(_lookup(entries, ["Abbreviation"], "DriverId"))
    entries = entries.merge(sprint, on=keys, how="left")
    entries["Location"] = entries["Location"].map(normalize_location)
    return entries.sort_values(RACE_KEYS + ["QPosition"]).reset_index(drop=True)


def build_conditions(weather: pd.DataFrame, track_status: pd.DataFrame) -> pd.DataFrame:
    pre_race = weather[weather["SessionCode"] != "R"]
    cond = pre_race.groupby(RACE_KEYS).agg(
        WeekendRain=("Rainfall", "max"), TrackTempMean=("TrackTemp", "mean")).reset_index()
    cond["WeekendRain"] = cond["WeekendRain"].astype(float)

    race_ts = track_status[track_status["SessionCode"] == "R"].copy()
    race_ts["SC"] = race_ts["Status"].astype(str).eq("4")
    race_ts["VSC"] = race_ts["Status"].astype(str).eq("6")
    sc = race_ts.groupby(RACE_KEYS).agg(SCCount=("SC", "sum"), VSCCount=("VSC", "sum")).reset_index()
    return cond.merge(sc, on=RACE_KEYS, how="outer")


def build_laps(laps: pd.DataFrame) -> pd.DataFrame:
    laps = laps[laps["SessionCode"].isin(LAP_SESSIONS)]
    return laps[[c for c in LAP_COLS if c in laps.columns]].reset_index(drop=True)


def quality_report(entries: pd.DataFrame) -> None:
    races = entries.groupby("Season")["RoundNumber"].nunique()
    print("Races per season:", races.to_dict())
    dups = entries.duplicated(RACE_KEYS + ["DriverId"]).sum()
    print("Duplicate driver-race rows:", int(dups))
    nulls = entries[["QPosition", "GridPosition", "FinishPosition", "TeamId"]].isna().mean().mul(100).round(1)
    print("Null %:", nulls.to_dict())


def load_power_units() -> pd.DataFrame:
    return pd.read_csv(config.POWER_UNITS_PATH)


def data_checks(entries: pd.DataFrame, conditions: pd.DataFrame, laps: pd.DataFrame,
                power_units: pd.DataFrame | None = None) -> list[str]:
    issues = []
    per_race = entries.groupby(RACE_KEYS).agg(
        EventName=("EventName", "first"),
        Entries=("DriverId", "size"),
        HasQuali=("QPosition", lambda s: s.notna().any()),
        HasResult=("FinishPosition", lambda s: s.notna().any()),
    )
    lap_races = set(map(tuple, laps[RACE_KEYS].drop_duplicates().to_numpy()))
    condition_races = set(map(tuple, conditions[RACE_KEYS].drop_duplicates().to_numpy()))
    latest = per_race.index.max()

    for (season, rnd), race in per_race.iterrows():
        label = f"{season} R{rnd:02d} {race['EventName']}"
        if race["Entries"] < MIN_ENTRIES:
            issues.append(f"{label}: only {race['Entries']} entries")
        if not race["HasQuali"]:
            issues.append(f"{label}: no qualifying results")
        # The latest race may simply not have happened yet.
        if not race["HasResult"] and (season, rnd) != latest:
            issues.append(f"{label}: no race results")
        if (season, rnd) not in lap_races:
            issues.append(f"{label}: no practice or sprint laps")
        if (season, rnd) not in condition_races:
            issues.append(f"{label}: no weather or track status")

    for event, locations in entries.groupby("EventName")["Location"].unique().items():
        if len(locations) > 1 and event not in config.DIFFERENT_VENUES:
            issues.append(f"{event}: held at {', '.join(sorted(locations))}; "
                          "add LOCATION_ALIASES in config if these are the same track")

    if power_units is not None:
        listed = set(map(tuple, power_units[["Season", "TeamId"]].to_numpy()))
        for season, team in entries[["Season", "TeamId"]].dropna().drop_duplicates().itertuples(index=False):
            if (season, team) not in listed:
                issues.append(f"{season} {team}: no power unit in {config.POWER_UNITS_PATH.name}")
    return issues


def load_processed() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return tuple(pd.read_parquet(config.PROCESSED_DIR / f"{name}.parquet")
                 for name in ["entries", "laps", "conditions"])


def run() -> None:
    results = _read("results")
    entries = build_entries(results)
    conditions = build_conditions(_read("weather"), _read("track_status"))
    laps = build_laps(_read("laps"))

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    entries.to_parquet(config.PROCESSED_DIR / "entries.parquet", index=False)
    conditions.to_parquet(config.PROCESSED_DIR / "conditions.parquet", index=False)
    laps.to_parquet(config.PROCESSED_DIR / "laps.parquet", index=False)
    print(f"entries={len(entries)} conditions={len(conditions)} laps={len(laps)}")
    quality_report(entries)
    issues = data_checks(entries, conditions, laps, load_power_units())
    print(f"Data checks: {len(issues)} issue(s)" if issues else "Data checks: OK")
    for issue in issues:
        print(f"  - {issue}")

"""Driver-race feature rows using only pre-race information."""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1pred import config

RACE_KEYS = ["Season", "RoundNumber"]
OUTCOME_COLS = ["FinishPosition", "Classified", "Status", "Points", "RaceLaps"]
CONDITION_OUTCOME_COLS = ["SCCount", "VSCCount"]
DNF_CODES = {"R", "D", "E", "N", "F"}

_GRID = ["Grid", "GridPitlane"]

# Grid + qualifying was the only set to beat the grid baseline on the full 2022-2026 backtest.
FEATURES = _GRID + ["QPosition", "QGapPct", "QGapTeammatePct"]

ALL_FEATURES = FEATURES + [
    "SprintPosition", "SprintGain",
    "LongRunPct", "LongRunRank", "LongRunTeammatePct", "LongRunLaps",
    "DrvFinishLast3", "DrvFinishLast5", "DrvPointsLast5", "DrvGainLast5", "DrvDnfSeason",
    "TeamBestFinishLast3", "TeamQPosLast3",
    "DrvGainCareer", "DrvDnfCareer", "DrvH2HCareer",
    "TrkGridFinishCorr", "TrkSCRate",
    "WeekendRain", "TrackTempMean", "EraIndex", "RacesIntoEra", "NStarters",
]

# Identical for every driver in a race, so a within-race ranker can only use them via interactions.
RACE_CONSTANT_FEATURES = [
    "TrkGridFinishCorr", "TrkSCRate", "WeekendRain", "TrackTempMean", "EraIndex", "RacesIntoEra", "NStarters",
]

# Candidate features kept out of FEATURES until a full-data backtest shows they help.
PU_FEATURES = ["PuQPosLast3", "PuFinishLast3"]
PENALTY_FEATURES = ["GridMinusQuali"]
PRACTICE_FEATURES = ["PracticeGapPct", "PracticeRank", "PracticeTeammatePct", "PracticeMinusQuali"]
PRACTICE_SESSIONS = ["FP1", "FP2", "FP3"]

_PACE = FEATURES + ["LongRunPct", "LongRunRank", "LongRunTeammatePct", "LongRunLaps", "SprintPosition", "SprintGain"]
FEATURE_SETS = {
    "grid": _GRID,
    "quali": FEATURES,
    "pace": _PACE,
    "pace_pu": _PACE + PU_FEATURES,
    "no_race_constants": [f for f in ALL_FEATURES if f not in RACE_CONSTANT_FEATURES],
    "all": ALL_FEATURES,
    "all_pu": ALL_FEATURES + PU_FEATURES,
    "quali_pen": FEATURES + PENALTY_FEATURES,
    "all_pen": ALL_FEATURES + PENALTY_FEATURES,
    "quali_practice": FEATURES + PRACTICE_FEATURES,
    "pace_practice": _PACE + PRACTICE_FEATURES,
}


def _clean_laps(laps: pd.DataFrame) -> pd.DataFrame:
    return laps[
        laps["IsAccurate"].eq(True)
        & ~laps["Deleted"].eq(True)
        & laps["PitInTimeSeconds"].isna()
        & laps["PitOutTimeSeconds"].isna()
        & laps["TrackStatus"].astype(str).eq("1")
        & laps["LapTimeSeconds"].notna()
    ]


def practice_pace(laps: pd.DataFrame) -> pd.DataFrame:
    clean = _clean_laps(laps[laps["SessionCode"].isin(PRACTICE_SESSIONS)])
    best = clean.groupby(RACE_KEYS + ["SessionCode", "Driver"])["LapTimeSeconds"].min().reset_index()
    fastest = best.groupby(RACE_KEYS + ["SessionCode"])["LapTimeSeconds"].transform("min")
    best["Gap"] = (best["LapTimeSeconds"] / fastest - 1) * 100
    pace = best.groupby(RACE_KEYS + ["Driver"]).agg(
        PracticeGapPct=("Gap", "min"), PracticeSessions=("Gap", "size"))
    return pace.reset_index().rename(columns={"Driver": "Abbreviation"})


def long_run_pace(laps: pd.DataFrame) -> pd.DataFrame:
    clean = _clean_laps(laps)
    clean = clean[~(clean["SessionCode"].eq("S") & clean["LapNumber"].le(1))]
    stint_keys = RACE_KEYS + ["SessionCode", "Driver", "Stint", "Compound"]
    stint_median = clean.groupby(stint_keys)["LapTimeSeconds"].transform("median")
    clean = clean[clean["LapTimeSeconds"] <= stint_median * 1.04]

    stints = clean.groupby(stint_keys).agg(
        Pace=("LapTimeSeconds", "median"), Laps=("LapTimeSeconds", "size"),
    ).reset_index()
    stints = stints[stints["Laps"] >= 5]
    ref_keys = RACE_KEYS + ["SessionCode", "Compound"]
    stints = stints[stints.groupby(ref_keys)["Pace"].transform("size") >= 3].copy()
    stints["Pct"] = (stints["Pace"] / stints.groupby(ref_keys)["Pace"].transform("median") - 1) * 100
    stints["Weighted"] = stints["Pct"] * stints["Laps"]

    pace = stints.groupby(RACE_KEYS + ["Driver"]).agg(
        Weighted=("Weighted", "sum"), LongRunLaps=("Laps", "sum"),
    )
    pace["LongRunPct"] = pace.pop("Weighted") / pace["LongRunLaps"]
    return pace.reset_index().rename(columns={"Driver": "Abbreviation"})


def _teammate_gap(df: pd.DataFrame, col: str) -> pd.Series:
    grp = df.groupby(RACE_KEYS + ["TeamId"])[col]
    others = (grp.transform("sum") - df[col]) / (grp.transform("count") - df[col].notna())
    return (df[col] / others - 1) * 100


def _prior_rolling(df: pd.DataFrame, by: list[str], col: str, window: int | None) -> pd.Series:
    def f(s: pd.Series) -> pd.Series:
        s = s.shift(1)
        return s.expanding().mean() if window is None else s.rolling(window, min_periods=1).mean()
    return df.groupby(by, group_keys=False)[col].apply(f)


def _race_order(df: pd.DataFrame) -> pd.Series:
    order = df[RACE_KEYS].drop_duplicates().sort_values(RACE_KEYS).reset_index(drop=True)
    order["RaceIdx"] = np.arange(len(order))
    return df[RACE_KEYS].merge(order, on=RACE_KEYS, how="left")["RaceIdx"].to_numpy()


def _per_race_history(race_level: pd.DataFrame, by: list[str], cols: dict[str, tuple[str, int | None]]) -> pd.DataFrame:
    race_level = race_level.sort_values("RaceIdx")
    out = race_level[list(dict.fromkeys(RACE_KEYS + by))].copy()
    for new, (src, window) in cols.items():
        out[new] = _prior_rolling(race_level, by, src, window)
    return out


def build_features(entries: pd.DataFrame, laps: pd.DataFrame, conditions: pd.DataFrame,
                   power_units: pd.DataFrame | None = None) -> pd.DataFrame:
    if power_units is None:
        power_units = pd.read_csv(config.POWER_UNITS_PATH)
    df = entries.copy()
    df["RaceIdx"] = _race_order(df)
    df = df.sort_values(["RaceIdx", "QPosition"]).reset_index(drop=True)

    df["NStarters"] = df.groupby(RACE_KEYS)["DriverId"].transform("size")
    df["Grid"] = df["GridPosition"].fillna(df["QPosition"])
    df["GridPitlane"] = df["Grid"].eq(0).astype(float)
    df.loc[df["Grid"].eq(0), "Grid"] = df["NStarters"]
    df["GridMinusQuali"] = df["Grid"] - df["QPosition"]

    df["QGapPct"] = (df["QBestSeconds"] / df.groupby(RACE_KEYS)["QBestSeconds"].transform("min") - 1) * 100
    df["QGapTeammatePct"] = _teammate_gap(df, "QBestSeconds")
    df["SprintGain"] = df["SprintGrid"] - df["SprintPosition"]

    pace = long_run_pace(laps)
    df = df.merge(pace, on=RACE_KEYS + ["Abbreviation"], how="left")
    df["LongRunRank"] = df.groupby(RACE_KEYS)["LongRunPct"].rank()
    df["LongRunTeammatePct"] = df["LongRunPct"] - (
        df.groupby(RACE_KEYS + ["TeamId"])["LongRunPct"].transform("sum") - df["LongRunPct"]
    ) / (df.groupby(RACE_KEYS + ["TeamId"])["LongRunPct"].transform("count") - 1)

    df = df.merge(practice_pace(laps), on=RACE_KEYS + ["Abbreviation"], how="left")
    df["PracticeRank"] = df.groupby(RACE_KEYS)["PracticeGapPct"].rank()
    df["PracticeTeammatePct"] = df["PracticeGapPct"] - (
        df.groupby(RACE_KEYS + ["TeamId"])["PracticeGapPct"].transform("sum") - df["PracticeGapPct"]
    ) / (df.groupby(RACE_KEYS + ["TeamId"])["PracticeGapPct"].transform("count") - 1)
    df["PracticeMinusQuali"] = df["PracticeRank"] - df["QPosition"]

    df["Gain"] = df["Grid"] - df["FinishPosition"]
    classified = df["Classified"].astype("string")
    df["Dnf"] = classified.isin(DNF_CODES).astype(float).where(classified.notna())
    team_rank = df.groupby(RACE_KEYS + ["TeamId"])["FinishPosition"].rank()
    team_size = df.groupby(RACE_KEYS + ["TeamId"])["FinishPosition"].transform("count")
    df["BeatTeammate"] = team_rank.eq(1).astype(float).where(team_size.eq(2))

    df = df.sort_values(["RaceIdx", "QPosition"]).reset_index(drop=True)
    df["DrvFinishLast3"] = _prior_rolling(df, ["Season", "DriverId"], "FinishPosition", 3)
    df["DrvFinishLast5"] = _prior_rolling(df, ["Season", "DriverId"], "FinishPosition", 5)
    df["DrvPointsLast5"] = _prior_rolling(df, ["Season", "DriverId"], "Points", 5)
    df["DrvGainLast5"] = _prior_rolling(df, ["Season", "DriverId"], "Gain", 5)
    df["DrvDnfSeason"] = _prior_rolling(df, ["Season", "DriverId"], "Dnf", None)
    df["DrvGainCareer"] = _prior_rolling(df, ["DriverId"], "Gain", None)
    df["DrvDnfCareer"] = _prior_rolling(df, ["DriverId"], "Dnf", None)
    df["DrvH2HCareer"] = _prior_rolling(df, ["DriverId"], "BeatTeammate", None)

    team_race = df.groupby(RACE_KEYS + ["RaceIdx", "TeamId"]).agg(
        BestFinish=("FinishPosition", "min"), MeanQPos=("QPosition", "mean")).reset_index()
    team_hist = _per_race_history(team_race, ["Season", "TeamId"], {
        "TeamBestFinishLast3": ("BestFinish", 3), "TeamQPosLast3": ("MeanQPos", 3)})
    df = df.merge(team_hist, on=RACE_KEYS + ["TeamId"], how="left")

    df = df.merge(power_units[["Season", "TeamId", "PowerUnit"]], on=["Season", "TeamId"], how="left")
    pu_race = df.groupby(RACE_KEYS + ["RaceIdx", "PowerUnit"]).agg(
        MeanQPos=("QPosition", "mean"), MeanFinish=("FinishPosition", "mean")).reset_index()
    pu_hist = _per_race_history(pu_race, ["Season", "PowerUnit"], {
        "PuQPosLast3": ("MeanQPos", 3), "PuFinishLast3": ("MeanFinish", 3)})
    df = df.merge(pu_hist, on=RACE_KEYS + ["PowerUnit"], how="left")

    def grid_finish_corr(g: pd.DataFrame) -> float:
        g = g.dropna(subset=["Grid", "FinishPosition"])
        return g["Grid"].corr(g["FinishPosition"], method="spearman") if len(g) > 2 else np.nan

    race_level = df.groupby(RACE_KEYS + ["RaceIdx", "Location"]).apply(
        grid_finish_corr, include_groups=False).rename("GridFinishCorr").reset_index()
    race_level = race_level.merge(conditions, on=RACE_KEYS, how="left")
    race_level["HadSC"] = ((race_level["SCCount"] + race_level["VSCCount"]) > 0).astype(float).where(
        race_level["SCCount"].notna())
    track_hist = _per_race_history(race_level, ["Location"], {
        "TrkGridFinishCorr": ("GridFinishCorr", None), "TrkSCRate": ("HadSC", None)})
    df = df.merge(track_hist.drop(columns="Location"), on=RACE_KEYS, how="left")

    df = df.merge(conditions.drop(columns=CONDITION_OUTCOME_COLS, errors="ignore"), on=RACE_KEYS, how="left")
    df["EraIndex"] = df["Season"].map(config.era_index)
    era_first_idx = df.groupby("EraIndex")["RaceIdx"].transform("min")
    df["RacesIntoEra"] = (df["RaceIdx"] - era_first_idx).astype(float)

    df = df.sort_values(["RaceIdx", "QPosition"]).reset_index(drop=True)
    for col in ALL_FEATURES + PU_FEATURES + PENALTY_FEATURES + PRACTICE_FEATURES:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    return df

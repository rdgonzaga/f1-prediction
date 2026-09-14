import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from f1pred.features import CONDITION_OUTCOME_COLS, FEATURES, OUTCOME_COLS, build_features, long_run_pace

TEAMS = ["red", "blue", "green"]
LOCATIONS = ["Sakhir", "Jeddah", "Melbourne", "Suzuka"]


def make_data(seed: int = 0):
    rng = np.random.default_rng(seed)
    entries, laps, conditions = [], [], []
    drivers = [(f"d{i}", f"D{i:02d}", TEAMS[i // 2]) for i in range(6)]
    for season in [2024, 2025, 2026]:
        for rnd in range(1, 5):
            quali = rng.permutation(6) + 1
            grid = quali.copy()
            finish = rng.permutation(6) + 1
            for (driver_id, abbr, team), q, g, f in zip(drivers, quali, grid, finish):
                entries.append({
                    "Season": season, "RoundNumber": rnd, "EventName": f"GP {rnd}",
                    "EventFormat": "conventional", "Location": LOCATIONS[rnd - 1],
                    "DriverId": driver_id, "Abbreviation": abbr, "TeamId": team, "TeamName": team,
                    "QPosition": float(q), "QBestSeconds": 90 + q * 0.1 + rng.random() * 0.05,
                    "GridPosition": float(g), "FinishPosition": float(f),
                    "Classified": "R" if f == 6 else str(f), "Status": "Finished",
                    "Points": float(max(0, 10 - f)), "RaceLaps": 50.0,
                    "SprintPosition": np.nan, "SprintGrid": np.nan,
                })
                for lap in range(1, 9):
                    laps.append({
                        "Season": season, "RoundNumber": rnd, "SessionCode": "FP2", "Driver": abbr,
                        "Team": team, "LapNumber": float(lap), "Stint": 1.0, "Compound": "MEDIUM",
                        "TyreLife": float(lap), "LapTimeSeconds": 95 + q * 0.1 + rng.random() * 0.2,
                        "PitInTimeSeconds": np.nan,
                        "PitOutTimeSeconds": 10.0 if lap == 1 else np.nan,
                        "TrackStatus": "1", "IsAccurate": True, "Deleted": False,
                    })
            conditions.append({
                "Season": season, "RoundNumber": rnd, "WeekendRain": 0.0,
                "TrackTempMean": 30 + rnd, "SCCount": float(rng.integers(0, 2)), "VSCCount": 0.0,
            })
    return pd.DataFrame(entries), pd.DataFrame(laps), pd.DataFrame(conditions)


def test_features_do_not_use_target_race_outcome():
    entries, laps, conditions = make_data()
    target = (2026, 3)

    full = build_features(entries, laps, conditions)

    keep = (entries["Season"] * 100 + entries["RoundNumber"]) <= target[0] * 100 + target[1]
    truncated = entries[keep].copy()
    is_target = (truncated["Season"] == target[0]) & (truncated["RoundNumber"] == target[1])
    truncated.loc[is_target, OUTCOME_COLS] = np.nan
    cond = conditions.copy()
    cond_target = (cond["Season"] == target[0]) & (cond["RoundNumber"] == target[1])
    cond.loc[cond_target, CONDITION_OUTCOME_COLS] = np.nan
    blind = build_features(truncated, laps, cond)

    def pick(df):
        rows = df[(df["Season"] == target[0]) & (df["RoundNumber"] == target[1])]
        return rows.sort_values("DriverId")[["DriverId"] + FEATURES].reset_index(drop=True)

    pdt.assert_frame_equal(pick(full), pick(blind))


def test_one_row_per_driver_race_and_all_features_numeric():
    entries, laps, conditions = make_data()
    feats = build_features(entries, laps, conditions)
    assert len(feats) == len(entries)
    assert not feats.duplicated(["Season", "RoundNumber", "DriverId"]).any()
    assert all(feats[c].dtype == float for c in FEATURES)


def test_first_race_has_no_history():
    entries, laps, conditions = make_data()
    feats = build_features(entries, laps, conditions)
    first = feats[(feats["Season"] == 2024) & (feats["RoundNumber"] == 1)]
    assert first[["DrvFinishLast3", "DrvGainCareer", "TrkSCRate", "TeamBestFinishLast3"]].isna().all().all()


def test_long_run_degradation_ranks_drivers_by_relative_slope():
    slopes = {"AAA": 0.02, "BBB": 0.05, "CCC": 0.10, "DDD": 0.15}
    laps = pd.DataFrame([{
        "Season": 2026, "RoundNumber": 1, "SessionCode": "FP2", "Driver": driver, "Team": "t",
        "LapNumber": float(lap), "Stint": 1.0, "Compound": "MEDIUM", "TyreLife": float(lap),
        "LapTimeSeconds": 90 + slope * lap, "PitInTimeSeconds": np.nan,
        "PitOutTimeSeconds": 10.0 if lap == 1 else np.nan, "TrackStatus": "1", "IsAccurate": True, "Deleted": False,
    } for driver, slope in slopes.items() for lap in range(1, 9)])

    deg = long_run_pace(laps).set_index("Abbreviation")["LongRunDeg"]
    median = np.median(list(slopes.values()))
    for driver, slope in slopes.items():
        assert deg[driver] == pytest.approx(slope - median, abs=1e-9)


def test_long_run_pace_excludes_out_laps_and_short_stints():
    _, laps, _ = make_data()
    one_race = laps[(laps["Season"] == 2024) & (laps["RoundNumber"] == 1)]
    pace = long_run_pace(one_race)
    assert len(pace) == 6
    assert (pace["LongRunLaps"] <= 7).all()

    short = one_race[one_race["LapNumber"] <= 4]
    assert long_run_pace(short).empty

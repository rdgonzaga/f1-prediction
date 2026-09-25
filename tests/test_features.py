import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from f1pred.features import (
    ALL_FEATURES, CONDITION_OUTCOME_COLS, OOP_FEATURES, OUTCOME_COLS, PENALTY_FEATURES, PRACTICE_FEATURES, PU_FEATURES,
    build_features,
    long_run_pace, practice_pace,
)

TEAMS = ["red", "blue", "green"]
LOCATIONS = ["Sakhir", "Jeddah", "Melbourne", "Suzuka"]
POWER_UNITS = pd.DataFrame([
    {"Season": season, "TeamId": team, "PowerUnit": "pu_b" if team == "green" or (team == "blue" and season == 2026)
     else "pu_a"}
    for season in [2024, 2025, 2026] for team in TEAMS
])


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

    full = build_features(entries, laps, conditions, POWER_UNITS)

    keep = (entries["Season"] * 100 + entries["RoundNumber"]) <= target[0] * 100 + target[1]
    truncated = entries[keep].copy()
    is_target = (truncated["Season"] == target[0]) & (truncated["RoundNumber"] == target[1])
    truncated.loc[is_target, OUTCOME_COLS] = np.nan
    cond = conditions.copy()
    cond_target = (cond["Season"] == target[0]) & (cond["RoundNumber"] == target[1])
    cond.loc[cond_target, CONDITION_OUTCOME_COLS] = np.nan
    blind = build_features(truncated, laps, cond, POWER_UNITS)

    def pick(df):
        rows = df[(df["Season"] == target[0]) & (df["RoundNumber"] == target[1])]
        cols = ["DriverId"] + ALL_FEATURES + PU_FEATURES + PENALTY_FEATURES + PRACTICE_FEATURES + OOP_FEATURES
        return rows.sort_values("DriverId")[cols].reset_index(drop=True)

    pdt.assert_frame_equal(pick(full), pick(blind))


def test_one_row_per_driver_race_and_all_features_numeric():
    entries, laps, conditions = make_data()
    feats = build_features(entries, laps, conditions)
    assert len(feats) == len(entries)
    assert not feats.duplicated(["Season", "RoundNumber", "DriverId"]).any()
    assert all(feats[c].dtype == float for c in ALL_FEATURES + PRACTICE_FEATURES + OOP_FEATURES)


def test_first_race_has_no_history():
    entries, laps, conditions = make_data()
    feats = build_features(entries, laps, conditions)
    first = feats[(feats["Season"] == 2024) & (feats["RoundNumber"] == 1)]
    assert first[["DrvFinishLast3", "DrvGainCareer", "TrkSCRate", "TeamBestFinishLast3"]].isna().all().all()


def test_power_unit_form_averages_prior_races_of_all_cars_with_that_pu():
    entries, laps, conditions = make_data()
    feats = build_features(entries, laps, conditions, POWER_UNITS)

    def expected(season, rnd, pu, col):
        teams = POWER_UNITS[(POWER_UNITS["Season"] == season) & (POWER_UNITS["PowerUnit"] == pu)]["TeamId"]
        prior = entries[(entries["Season"] == season) & entries["RoundNumber"].between(rnd - 3, rnd - 1)
                        & entries["TeamId"].isin(teams)]
        return prior.groupby("RoundNumber")[col].mean().mean()

    for season, rnd, team, pu in [(2025, 4, "red", "pu_a"), (2026, 3, "blue", "pu_b"), (2026, 2, "green", "pu_b")]:
        row = feats[(feats["Season"] == season) & (feats["RoundNumber"] == rnd) & (feats["TeamId"] == team)].iloc[0]
        assert row["PuQPosLast3"] == pytest.approx(expected(season, rnd, pu, "QPosition"))
        assert row["PuFinishLast3"] == pytest.approx(expected(season, rnd, pu, "FinishPosition"))

    season_start = feats[feats["RoundNumber"] == 1]
    assert season_start[PU_FEATURES].isna().all().all()


def test_grid_minus_quali_reflects_penalties_and_pit_lane():
    entries, laps, conditions = make_data()
    race = (entries["Season"] == 2026) & (entries["RoundNumber"] == 2)
    penalised = race & entries["QPosition"].eq(1)
    pitlane = race & entries["QPosition"].eq(3)
    missing = race & entries["QPosition"].eq(4)
    entries.loc[penalised, "GridPosition"] = 6.0
    entries.loc[pitlane, "GridPosition"] = 0.0
    entries.loc[missing, "GridPosition"] = np.nan

    feats = build_features(entries, laps, conditions, POWER_UNITS).set_index(["Season", "RoundNumber", "QPosition"])
    assert feats.loc[(2026, 2, 1.0), "GridMinusQuali"] == 5
    assert feats.loc[(2026, 2, 3.0), "GridMinusQuali"] == 6 - 3
    assert feats.loc[(2026, 2, 4.0), "GridMinusQuali"] == 0
    assert feats.loc[(2026, 2, 2.0), "GridMinusQuali"] == 0


def test_long_run_pace_excludes_out_laps_and_short_stints():
    _, laps, _ = make_data()
    one_race = laps[(laps["Season"] == 2024) & (laps["RoundNumber"] == 1)]
    pace = long_run_pace(one_race)
    assert len(pace) == 6
    assert (pace["LongRunLaps"] <= 7).all()

    short = one_race[one_race["LapNumber"] <= 4]
    assert long_run_pace(short).empty


def test_practice_pace_uses_best_clean_lap_per_session():
    _, laps, _ = make_data()
    one_race = laps[(laps["Season"] == 2024) & (laps["RoundNumber"] == 1)].copy()
    slowest = one_race.groupby("Driver")["LapTimeSeconds"].min().idxmax()
    dirty = one_race["Driver"].eq(slowest) & one_race["LapNumber"].isin([2, 3, 4])
    one_race.loc[dirty, "LapTimeSeconds"] = 80.0
    one_race.loc[dirty & one_race["LapNumber"].eq(2), "Deleted"] = True
    one_race.loc[dirty & one_race["LapNumber"].eq(3), "PitInTimeSeconds"] = 50.0
    one_race.loc[dirty & one_race["LapNumber"].eq(4), "TrackStatus"] = "4"

    pace = practice_pace(one_race).set_index("Abbreviation")
    assert pace["PracticeGapPct"].min() == 0
    assert pace["PracticeGapPct"].idxmax() == slowest
    assert (pace["PracticeSessions"] == 1).all()


def test_fast_in_practice_slow_in_quali_has_negative_practice_minus_quali():
    entries, laps, conditions = make_data()
    race = (laps["Season"] == 2026) & (laps["RoundNumber"] == 2)
    target = entries[(entries["Season"] == 2026) & (entries["RoundNumber"] == 2)]
    last = target.loc[target["QPosition"].idxmax(), "Abbreviation"]
    laps.loc[race & laps["Driver"].eq(last), "LapTimeSeconds"] -= 5

    feats = build_features(entries, laps, conditions, POWER_UNITS)
    row = feats[(feats["Season"] == 2026) & (feats["RoundNumber"] == 2) & (feats["Abbreviation"] == last)].iloc[0]
    assert row["PracticeGapPct"] == 0
    assert row["PracticeRank"] == 1
    assert row["PracticeMinusQuali"] == 1 - row["QPosition"] < 0


def test_fast_driver_starting_at_the_back_is_out_of_position():
    entries, laps, conditions = make_data()
    target = (entries["Season"] == 2026) & (entries["RoundNumber"] == 3)
    prior = (entries["Season"] == 2026) & (entries["RoundNumber"] < 3)
    entries.loc[prior & entries["Abbreviation"].eq("D00"), "FinishPosition"] = 1.0
    last = entries.loc[target, "QPosition"].max()
    entries.loc[target & entries["Abbreviation"].eq("D00"), ["QPosition", "GridPosition"]] = last
    race = (laps["Season"] == 2026) & (laps["RoundNumber"] == 3)
    laps.loc[race & laps["Driver"].eq("D00"), "LapTimeSeconds"] -= 5

    feats = build_features(entries, laps, conditions, POWER_UNITS)
    row = feats[(feats["Season"] == 2026) & (feats["RoundNumber"] == 3) & (feats["Abbreviation"] == "D00")].iloc[0]
    assert row["ExpectedRank"] <= 2
    assert row["OutOfPosition"] >= last - 2

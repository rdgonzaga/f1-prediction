import numpy as np
import pandas as pd
import pytest

from f1pred.predict import (
    apply_grid_penalties, guard_already_run, headline, markdown_table, parse_penalties,
)


def quali(codes):
    return pd.DataFrame({"Abbreviation": codes, "QPosition": np.arange(1.0, len(codes) + 1)})


def grid_order(race, grid):
    starters = grid[grid > 0].sort_values()
    return list(race.loc[starters.index, "Abbreviation"]), list(race.loc[grid[grid == 0].index, "Abbreviation"])


def test_place_penalty_and_pitlane():
    race = quali(["A", "B", "C", "D", "E"])
    grid = apply_grid_penalties(race, {"B": 2}, {"D"})
    assert grid_order(race, grid) == (["A", "C", "B", "E"], ["D"])
    assert list(grid[grid > 0].sort_values()) == [1, 2, 3, 4]


def test_penalised_driver_goes_behind_tied_driver_and_can_reach_the_back():
    race = quali(["A", "B", "C", "D"])
    assert grid_order(race, apply_grid_penalties(race, {"A": 1}, set()))[0] == ["B", "A", "C", "D"]
    assert grid_order(race, apply_grid_penalties(race, {"B": 10}, set()))[0] == ["A", "C", "D", "B"]


def test_no_quali_time_starts_at_back_unless_a_penalty_pushes_further():
    race = pd.DataFrame({"Abbreviation": ["A", "B", "C"], "QPosition": [1.0, np.nan, 2.0]})
    assert grid_order(race, apply_grid_penalties(race, {}, {"C"}))[0] == ["A", "B"]
    assert grid_order(race, apply_grid_penalties(race, {"A": 1}, set()))[0] == ["C", "A", "B"]
    assert grid_order(race, apply_grid_penalties(race, {"A": 5}, set()))[0] == ["C", "B", "A"]


def test_bad_penalty_input_is_rejected():
    assert parse_penalties(["ver=5", "NOR=3"]) == {"VER": 5, "NOR": 3}
    with pytest.raises(SystemExit):
        parse_penalties(["VER5"])
    with pytest.raises(SystemExit):
        apply_grid_penalties(quali(["A", "B"]), {"ZZZ": 3}, set())


def test_refuses_a_race_that_already_ran():
    race = pd.DataFrame({"FinishPosition": [1.0, 2.0, np.nan]})
    with pytest.raises(SystemExit) as error:
        guard_already_run(race, 2026, 15, backfill=False)
    assert "round 15" in str(error.value)
    assert "--backfill" in str(error.value)


def test_backfill_overrides_the_refusal():
    race = pd.DataFrame({"FinishPosition": [1.0, 2.0, np.nan]})
    assert guard_already_run(race, 2026, 15, backfill=True) is True


def test_upcoming_race_passes_the_guard():
    race = pd.DataFrame({"FinishPosition": [np.nan, np.nan]})
    assert guard_already_run(race, 2026, 15, backfill=False) is False


def test_markdown_table_and_headline():
    out = pd.DataFrame({
        "PredictedPosition": [1, 2, 3, 4],
        "Abbreviation": ["ANT", "NOR", "VER", "RUS"],
        "WinPct": [59.2, 9.4, 8.2, 7.2],
        "PodiumPct": [90.6, 44.2, 37.6, 42.4],
    })
    table = markdown_table(out).splitlines()
    assert table[0] == "| PredictedPosition | Abbreviation | WinPct | PodiumPct |"
    assert table[1] == "|---|---|---|---|"
    assert table[2] == "| 1 | ANT | 59.2 | 90.6 |"
    assert len(table) == 6
    assert headline(out) == "Favourite: ANT (59% win) | Most likely podium: ANT, NOR, RUS"

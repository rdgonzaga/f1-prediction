import pandas as pd
import pytest

from f1pred import report, score
from f1pred.web import data
from test_score import actual_frame, pred_frame


def make_race(pred=None, actual=None, **kw):
    return data.race(2026, 1, pred if pred is not None else pred_frame(pre_race=True),
                     actual if actual is not None else actual_frame(), **kw)


def test_ordinal():
    assert [data.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]


def test_verdict_when_the_favourite_wins():
    race = make_race()
    assert race.winner == "A" and race.pick_hit
    assert race.verdict.lines == ["A won as favourite at 50%", "2 of 3 podium spots called",
                                  "Biggest surprise: D, 4th to 3rd"]


def test_verdict_when_the_favourite_retires():
    race = make_race(actual=actual_frame().assign(Classified=["R", "1", "2", "3"]))
    assert not race.pick_hit
    assert race.verdict.lines == ["Favourite A (50%) retired", "2 of 3 podium spots called",
                                  "Biggest surprise: B, 2nd to 1st"]


def test_verdict_when_the_favourite_is_beaten():
    race = make_race(actual=actual_frame().assign(Classified=["3", "1", "2", "R"]))
    assert race.verdict.lines[0] == "Favourite A (50%) finished 3rd"
    assert race.verdict.lines[1] == "3 of 3 podium spots called"


def test_exact_order_has_no_surprise():
    race = make_race(actual=actual_frame().assign(Classified=["1", "2", "3", "4"]))
    assert race.verdict.surprise is None
    assert len(race.verdict.lines) == 2


def test_pending_race_has_no_verdict_or_winner():
    race = make_race(actual=actual_frame().assign(Classified=""))
    assert race.pending and race.verdict is None and race.winner is None
    assert all(r.finish is None for r in race.rows)
    assert race.card_color == race.favourite.color


def test_old_csv_without_optional_columns_falls_back():
    race = make_race(ids={"A": "alpha"})
    a = race.rows[0]
    assert race.name == "Test Grand Prix"
    assert a.driver_id == "alpha" and race.rows[1].driver_id == "b"
    assert a.team == "" and a.color == report.team_colors("")[1]
    assert a.points is None and a.dnf is None
    assert race.made == "" and race.notes == [] and race.warnings == []
    assert data.race(2026, 7, pred_frame(), actual_frame().iloc[0:0]).name == "Round 7"


def test_winner_missing_from_the_prediction_still_counts():
    race = make_race(actual=actual_frame().assign(Abbreviation=["Z", "B", "C", "D"], TeamName="Ferrari"))
    assert race.winner == "Z" and not race.pick_hit
    assert race.card_color == report.team_colors("Ferrari")[1]
    assert race.rows[0].finish is None


def test_grid_labels_and_moves():
    rows = make_race(pred=pred_frame().assign(Grid=[0.0, 1.0, None, 4.0])).rows
    assert [r.grid_label for r in rows] == ["PIT", "1", "—", "4"]
    assert [r.move for r in rows] == [0, -1, 0, 0]


def test_notes_and_stamp_come_from_the_csv():
    pred = pred_frame(pre_race=True).assign(
        EventName="Azerbaijan Grand Prix", PredictedAtUTC="2026-09-25 16:16:37",
        GridOverrides="Grid overrides: ALO +30", Temperature=0.42, CalibrationRaces=12,
        Warnings="no weather; no track status")
    race = make_race(pred=pred)
    assert race.live and race.short_name == "Azerbaijan" and race.path == "2026/round-01/"
    assert race.made == "Fri 25 Sep 2026, 16:16 UTC · 00:16 Manila"
    assert race.notes == ["Grid overrides: ALO +30", "Probability spread 0.42, calibrated on 12 earlier races."]
    assert race.warnings == ["no weather", "no track status"]

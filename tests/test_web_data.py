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


IDS = ["alpha", "bravo", "charlie", "delta"]


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(score.config, "PREDICTIONS_DIR", tmp_path)
    for rnd, pre_race in [(1, False), (2, True), (3, True)]:
        path = score.config.prediction_path(2026, rnd, ".csv")
        path.parent.mkdir(parents=True)
        pred = pred_frame(pre_race=pre_race).assign(TeamName="Ferrari")
        if rnd == 3:
            pred = pred.assign(TeamName=["McLaren", "Ferrari", "Ferrari", "Ferrari"])
        if rnd > 1:
            pred = pred.assign(DriverId=IDS)
        pred.to_csv(path, index=False)
    entries = pd.concat([actual_frame(rnd=1), actual_frame(rnd=2), actual_frame(rnd=3).assign(Classified="")],
                        ignore_index=True).assign(DriverId=IDS * 3)
    monkeypatch.setattr(score.build, "load_processed", lambda: (entries, None, None))
    return entries


def no_schedule(year):
    return pd.DataFrame()


def test_next_race_uses_the_schedule_and_survives_failures():
    schedule = pd.DataFrame({"RoundNumber": [17, 18, 19], "EventName": [
        "Singapore Grand Prix", "United States Grand Prix", "Mexico City Grand Prix"]})
    nxt = data.next_race(2026, 17, lambda year: schedule)
    assert (nxt.rnd, nxt.name, nxt.short_name) == (18, "United States Grand Prix", "United States")
    assert data.next_race(2026, 19, lambda year: schedule) is None

    def offline(year):
        raise ConnectionError("offline")
    assert data.next_race(2026, 17, offline) is None
    assert data.next_race(2026, 17, no_schedule) is None


def test_summary_marks_where_the_model_beats_the_grid():
    races = pd.DataFrame({
        "Live": [True, False], "Spearman": [.8, .6], "GridSpearman": [.5, .7],
        "WinnerHit": [1.0, 0.0], "GridWinnerHit": [0.0, 0.0],
        "PodiumHitRate": [1.0, 2 / 3], "GridPodiumHitRate": [2 / 3, 2 / 3],
        "MAE": [1.0, 2.0], "GridMAE": [1.5, 1.5], "WinnerWinPct": [50.0, 30.0]})
    heads, rows = data.summary(races)
    assert heads == ["All races (2)", "Live only (1)"]
    assert rows[0]["label"] == "Order match"
    assert rows[0]["cells"][0] == {"model": "0.70", "grid": "0.60", "better": True}
    assert rows[3]["cells"][0]["better"] is False
    assert rows[-1]["cells"][1] == {"model": "50%", "grid": "—", "better": False}


def test_load_groups_races_and_counts_picks(saved):
    site = data.load(score.load_predictions(), saved,
                     lambda year: pd.DataFrame({"RoundNumber": [4], "EventName": ["Next Grand Prix"]}))
    season = site.current
    assert season.year == 2026 and [r.rnd for r in season.races] == [1, 2, 3]
    assert [r.rnd for r in season.newest_first] == [3, 2, 1]
    assert [r.live for r in season.races] == [False, True, True]
    assert season.latest.rnd == 3 and season.latest.pending
    assert len(season.scored) == 2 and season.picks_right == 2
    assert season.next_race.rnd == 4
    assert season.scorecard.beat == 2 and season.scorecard.live_count == 1
    assert site.scorecard_season is season and season.scorecard_path == "2026/scorecard/"
    assert season.races[0].rows[0].driver_id == "alpha"
    assert data.scorecard(2030) is None


def test_display_name():
    assert data.display_name("max_verstappen") == "Max Verstappen"
    assert data.display_name("antonelli") == "Antonelli"


def test_driver_stats_follow_the_results(saved):
    site = data.load(score.load_predictions(), saved, no_schedule)
    drivers = {d.driver_id: d for d in site.drivers}
    assert sorted(drivers) == IDS
    a, c, d = drivers["alpha"], drivers["charlie"], drivers["delta"]
    assert (a.wins, a.podiums, a.favourite_races, a.favourite_scored, a.favourite_right) == (2, 2, 3, 2, 2)
    assert a.places_off == 0.0
    assert a.team == "McLaren" and a.entries[0].row.team == "Ferrari"
    assert a.name == "Alpha" and a.path == "drivers/alpha/"
    assert [e.race.rnd for e in a.chart_entries] == [1, 2, 3]
    assert c.places_off is None and c.podiums == 0
    assert d.podiums == 2 and d.places_off == 1.0

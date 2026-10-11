import pandas as pd
import pytest

from f1pred import score, season
from test_score import actual_frame, pred_frame


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(score.config, "PREDICTIONS_DIR", tmp_path)
    for rnd, pre_race in [(1, False), (2, True), (3, True)]:
        path = score.config.prediction_path(2026, rnd, ".csv")
        path.parent.mkdir(parents=True)
        pred_frame(pre_race=pre_race).to_csv(path, index=False)
    entries = pd.concat([actual_frame(rnd=1), actual_frame(rnd=2), actual_frame(rnd=3).assign(Classified="")],
                        ignore_index=True)
    monkeypatch.setattr(season.build, "load_processed", lambda: (entries, None, None))
    return tmp_path


def test_season_data_keeps_backfilled_and_skips_partial_results(saved):
    races, drivers = season.season_data(2026)
    assert list(races["RoundNumber"]) == [1, 2]
    assert list(races["Live"]) == [False, True]
    assert drivers["OnPodium"].sum() == 6


def test_podium_calibration_compares_said_and_did():
    drivers = pd.DataFrame({"PodiumPct": [90.0, 90.0, 2.0, 3.0], "OnPodium": [True, False, False, False]})
    cal = season.podium_calibration(drivers)
    assert list(cal.index) == ["0–5%", "80–100%"]
    assert cal.loc["80–100%", "Did"] == pytest.approx(50.0)
    assert cal.loc["0–5%", "N"] == 2


def test_run_writes_page_with_live_races_marked(saved):
    path = season.run(2026, png=False)
    page = path.read_text(encoding="utf-8")
    assert path.name == "2026_season.html"
    assert "LIVE" in page
    assert "2/2" in page

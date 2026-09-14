import pandas as pd
import pytest

from f1pred import score


def pred_frame(pre_race=None):
    df = pd.DataFrame({
        "PredictedPosition": [1, 2, 3, 4], "Abbreviation": ["A", "B", "C", "D"], "Grid": [2.0, 1.0, 3.0, 4.0],
        "WinPct": [50.0, 30.0, 15.0, 5.0], "PodiumPct": [90.0, 80.0, 70.0, 60.0],
    })
    return df if pre_race is None else df.assign(PreRace=pre_race)


def actual_frame(season=2026, rnd=1):
    return pd.DataFrame({
        "Season": season, "RoundNumber": rnd, "EventName": "Test Grand Prix",
        "Abbreviation": ["A", "B", "C", "D"], "FinishPosition": [1.0, 2.0, 4.0, 3.0],
        "Classified": ["1", "2", "R", "3"],
    })


def test_score_race_compares_model_and_grid():
    row = score.score_race(pred_frame(), actual_frame())
    assert row["WinnerHit"] == 1.0
    assert row["GridWinnerHit"] == 0.0
    assert row["PodiumHitRate"] == pytest.approx(2 / 3)
    assert row["WinnerWinPct"] == 50.0


def test_only_flagged_predictions_count_as_pre_race():
    assert score.is_pre_race(pred_frame(pre_race=True))
    assert not score.is_pre_race(pred_frame(pre_race=False))
    assert not score.is_pre_race(pred_frame())


def test_run_skips_backfilled_and_unfinished_races(tmp_path, monkeypatch):
    pred_frame(pre_race=True).to_csv(tmp_path / "2026_R01.csv", index=False)
    pred_frame().to_csv(tmp_path / "2026_R02.csv", index=False)
    pred_frame(pre_race=True).to_csv(tmp_path / "2026_R03.csv", index=False)
    entries = pd.concat([actual_frame(rnd=1), actual_frame(rnd=2)], ignore_index=True)
    monkeypatch.setattr(score, "PREDICTIONS_DIR", tmp_path)
    monkeypatch.setattr(score.build, "load_processed", lambda: (entries, None, None))

    card = score.run()
    assert list(card["RoundNumber"]) == [1]
    assert (tmp_path / "scorecard.csv").exists()

    assert list(score.run(include_backfilled=True)["RoundNumber"]) == [1, 2]

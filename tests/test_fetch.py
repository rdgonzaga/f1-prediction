import pandas as pd

from f1pred import fetch


def test_queue_for_a_round_not_yet_started_is_empty_but_has_columns(monkeypatch):
    schedule = pd.DataFrame([{
        "RoundNumber": 16, "EventName": "Bahrain Grand Prix", "EventFormat": "conventional",
        "Country": "Bahrain", "Location": "Sakhir", "Session1": "Practice 1",
        "Session1DateUtc": pd.Timestamp.now() + pd.Timedelta(days=7),
    }])
    monkeypatch.setattr(fetch.fastf1, "get_event_schedule", lambda season, include_testing: schedule)

    queue = fetch.build_queue([2026], rounds=[16])
    assert queue.empty
    assert list(queue.columns) == fetch.QUEUE_COLUMNS


def test_race_results_without_grid_are_refetched(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch.config, "RAW_DIR", tmp_path)
    (tmp_path / "2026").mkdir()
    pd.DataFrame({"GridPosition": [None, None], "Position": [1.0, 2.0]}).to_parquet(
        tmp_path / "2026" / "R17_R_results.parquet")
    pd.DataFrame({"GridPosition": [2.0, 1.0], "Position": [1.0, 2.0]}).to_parquet(
        tmp_path / "2026" / "R16_R_results.parquet")
    pd.DataFrame({"GridPosition": [None, None], "Position": [1.0, 2.0]}).to_parquet(
        tmp_path / "2026" / "R17_Q_results.parquet")

    assert fetch.sessions_missing_results() == {"2026_R17_R"}

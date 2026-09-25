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

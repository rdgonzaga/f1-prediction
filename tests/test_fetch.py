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


def _queue_row(code="R"):
    return pd.DataFrame([{
        "SessionKey": f"2026_R19_{code}", "Season": 2026, "RoundNumber": 19, "EventName": "Mexico City Grand Prix",
        "EventFormat": "conventional", "Country": "Mexico", "Location": "Mexico City",
        "SessionName": "Race", "SessionCode": code, "SessionStartUTC": pd.Timestamp("2026-11-01 20:00"),
    }], columns=fetch.QUEUE_COLUMNS)


def _setup_run(tmp_path, monkeypatch, code):
    monkeypatch.setattr(fetch.config, "RAW_DIR", tmp_path)
    monkeypatch.setattr(fetch.config, "LOG_PATH", tmp_path / "extraction_log.csv")
    monkeypatch.setattr(fetch.config, "RETRY_SLEEP_SECONDS", 0)
    monkeypatch.setattr(fetch, "enable_cache", lambda: None)
    monkeypatch.setattr(fetch, "build_queue", lambda *a, **k: _queue_row(code))

    def fail(job):
        raise RuntimeError("DataNotLoadedError")
    monkeypatch.setattr(fetch, "extract_session", fail)
    monkeypatch.setattr(fetch.official, "session_results", lambda *args: pd.DataFrame(
        {"Abbreviation": ["VER", "HAM"], "Position": [1.0, 2.0], "GridPosition": [5.0, 1.0]}))


def test_failed_fastf1_session_falls_back_to_official_results(tmp_path, monkeypatch):
    _setup_run(tmp_path, monkeypatch, "R")
    log = fetch.run([2026], rounds=[19], keep_cache=True)

    row = log.set_index("SessionKey").loc["2026_R19_R"]
    assert (row["Status"], row["Source"]) == ("DONE", "official")
    saved = pd.read_parquet(tmp_path / "2026" / "R19_R_results.parquet")
    assert saved["Abbreviation"].tolist() == ["VER", "HAM"]
    assert saved["SessionCode"].eq("R").all()

    calls = []
    monkeypatch.setattr(fetch, "extract_session", lambda job: calls.append(job) or {})
    log = fetch.run([2026], rounds=[19], keep_cache=True)
    assert len(calls) == 1
    assert log.set_index("SessionKey").loc["2026_R19_R", "Source"] == "fastf1"


def test_practice_sessions_have_no_fallback(tmp_path, monkeypatch):
    _setup_run(tmp_path, monkeypatch, "FP1")
    log = fetch.run([2026], rounds=[19], keep_cache=True)
    row = log.set_index("SessionKey").loc["2026_R19_FP1"]
    assert row["Status"] == "ERROR"
    assert not (tmp_path / "2026" / "R19_FP1_results.parquet").exists()

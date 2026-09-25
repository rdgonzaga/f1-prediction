import pandas as pd
import pytest

from f1pred import weekend


def log(status):
    return pd.DataFrame({"SessionKey": ["2026_R16_Q"], "Status": [status]})


@pytest.fixture
def calls(monkeypatch):
    calls = []
    monkeypatch.setattr(weekend.predict, "resolve_round", lambda season, event: int(event))
    monkeypatch.setattr(weekend.build, "run", lambda: calls.append("build"))
    monkeypatch.setattr(weekend.predict, "run", lambda *a, **k: calls.append(("predict", k["penalties"], k["pitlane"])))
    monkeypatch.setattr(weekend.report, "run", lambda season, rnd: calls.append(("report", season, rnd)) or "page")
    return calls


def test_runs_every_step_in_order_and_passes_penalties(monkeypatch, calls):
    monkeypatch.setattr(weekend.fetch, "run", lambda seasons, rounds: calls.append("fetch") or log("DONE"))

    assert weekend.run(2026, "16", penalties={"VER": 5}, pitlane=["STR"]) == "page"
    assert calls == ["fetch", "build", ("predict", {"VER": 5}, ["STR"]), ("report", 2026, 16)]


def test_stops_before_building_when_quali_is_missing(monkeypatch, calls):
    monkeypatch.setattr(weekend.fetch, "run", lambda seasons, rounds: log("ERROR"))

    with pytest.raises(SystemExit, match="isn't available yet"):
        weekend.run(2026, "16")
    assert calls == []


def test_wait_retries_until_quali_lands(monkeypatch, calls):
    statuses = iter(["ERROR", "ERROR", "DONE"])
    monkeypatch.setattr(weekend.fetch, "run", lambda seasons, rounds: log(next(statuses)))
    slept = []

    weekend.run(2026, "16", wait_minutes=60, sleep=slept.append)
    assert slept == [300, 300]
    assert calls[-1] == ("report", 2026, 16)

import pandas as pd
import pytest

from f1pred import runner
from f1pred.runner import RoundFiles

SESS = pd.DataFrame({
    "RoundNumber": [19, 20],
    "EventName": ["Mexico City Grand Prix", "São Paulo Grand Prix"],
    "QualiUTC": pd.to_datetime(["2026-10-31 21:00", "2026-11-07 18:00"], utc=True),
    "RaceUTC": pd.to_datetime(["2026-11-01 20:00", "2026-11-08 17:00"], utc=True),
})
NO_FIXES = {"penalties": None, "pitlane": None, "slots": None}
DONE = RoundFiles(grid_source="official", pre_race=True, market=True, scored=True)


def at(text):
    return pd.Timestamp(text, tz="UTC")


def step(now, **by_round):
    return runner.plan(SESS, at(now), lambda rnd: by_round.get(f"r{rnd}", RoundFiles()))


def test_before_the_season_waits_for_first_quali():
    s = step("2026-10-01")
    assert s.action == "wait" and "Mexico City Grand Prix qualifying" in s.message


def test_quali_still_running_waits():
    s = step("2026-11-07 18:30", r19=DONE)
    assert s.action == "wait" and "qualifying is on" in s.message


def test_quali_done_without_prediction_predicts():
    assert step("2026-11-07 20:00", r19=DONE).action == "predict"


def test_provisional_grid_is_rechecked_before_the_race():
    s = step("2026-11-08 10:00", r20=RoundFiles(grid_source="provisional", pre_race=True))
    assert (s.action, s.rnd) == ("regrid", 20)


@pytest.mark.parametrize("source", ["official", "openf1", "manual", ""])
def test_settled_prediction_waits_for_the_race(source):
    s = step("2026-11-08 10:00", r20=RoundFiles(grid_source=source, pre_race=True))
    assert s.action == "wait" and "Race starts" in s.message


def test_race_running_waits_for_results():
    assert step("2026-11-08 18:00", r20=RoundFiles(grid_source="official", pre_race=True)).action == "wait"


@pytest.mark.parametrize("files", [
    RoundFiles(grid_source="official", pre_race=True, market=False, scored=True),
    RoundFiles(grid_source="official", pre_race=True, market=True, scored=False),
    RoundFiles(market=False),
])
def test_after_the_race_scores_or_fetches_odds(files):
    assert step("2026-11-08 21:00", r20=files).action == "after_race"


def test_backfilled_prediction_with_odds_is_not_scored_again():
    files = RoundFiles(grid_source="official", pre_race=False, market=True, scored=False)
    assert step("2026-11-08 21:00", r20=files).action == "wait"


def test_scored_round_points_at_the_next_session():
    s = step("2026-11-02 12:00", r19=DONE)
    assert s.action == "wait" and "São Paulo Grand Prix qualifying" in s.message and "Sun 08 Nov 02:00" in s.message


def test_season_over():
    assert "No sessions left" in step("2026-11-09", r20=DONE).message


def test_sessions_cache_falls_back_when_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.config, "RAW_DIR", tmp_path)
    fresh = runner.sessions(2026, loader=lambda year: SESS)
    assert fresh["QualiUTC"].dt.tz is not None and (tmp_path / "sessions_2026.csv").exists()
    monkeypatch.setattr(runner, "SESSIONS_MAX_AGE", pd.Timedelta(0))

    def offline(year):
        raise ConnectionError

    cached = runner.sessions(2026, loader=offline)
    assert cached["EventName"].tolist() == SESS["EventName"].tolist()
    assert cached["RaceUTC"].equals(SESS["RaceUTC"])


@pytest.fixture
def calls(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(runner.config, "PREDICTIONS_DIR", tmp_path)
    monkeypatch.setattr(runner, "sessions", lambda season: SESS)
    monkeypatch.setattr(runner.weekend, "run", lambda season, event, wait_minutes, **grid: calls.append(("weekend", event, grid)))
    monkeypatch.setattr(runner.predict, "run", lambda season, event, refresh, **grid: calls.append(("predict", event, refresh, grid)))
    monkeypatch.setattr(runner.report, "run", lambda season, rnd: calls.append(("report", rnd)))
    monkeypatch.setattr(runner.web, "build_site", lambda: calls.append("site"))
    monkeypatch.setattr(runner.market, "run", lambda season, rounds: calls.append(("market", rounds)))
    monkeypatch.setattr(runner.score, "run", lambda season, refresh: calls.append("score") or pd.DataFrame({"a": [1]}))
    return calls


def test_run_predicts_through_weekend(calls):
    runner.run(2026, now=at("2026-11-07 20:00"))
    assert calls == [("weekend", "20", NO_FIXES)]


def test_run_after_race_fetches_odds_then_scores(calls):
    runner.run(2026, now=at("2026-11-08 21:00"))
    assert calls == [("market", [20]), "score", "site"]


def test_run_regrid_repredicts_without_refetching(calls, tmp_path):
    path = tmp_path / "2026" / "round_20" / "2026_R20.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame({"Abbreviation": ["RUS"], "PreRace": [True], "GridSource": ["provisional"]}).to_csv(path, index=False)
    runner.run(2026, now=at("2026-11-08 10:00"))
    assert calls == [("predict", "20", False, NO_FIXES), ("report", 20), "site"]


def test_run_passes_grid_fixes_to_weekend(calls):
    runner.run(2026, now=at("2026-11-07 20:00"), penalties={"VER": 5}, pitlane=["STR"])
    assert calls == [("weekend", "20", {"penalties": {"VER": 5}, "pitlane": ["STR"], "slots": None})]


def test_grid_fixes_repredict_a_settled_round(calls, tmp_path):
    path = tmp_path / "2026" / "round_20" / "2026_R20.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame({"Abbreviation": ["RUS"], "PreRace": [True], "GridSource": ["official"]}).to_csv(path, index=False)
    runner.run(2026, now=at("2026-11-08 10:00"), slots={"RUS": 19})
    assert calls == [("predict", "20", False, {"penalties": None, "pitlane": None, "slots": {"RUS": 19}}),
                     ("report", 20), "site"]


def fake_git(branch="main", changed="M site/index.html", push_fails=False):
    calls = []

    def run_git(*args):
        calls.append(args)
        if args[0] == "rev-parse":
            return branch
        if args[0] == "status":
            return changed
        if args[0] == "push" and push_fails and ("pull", "--rebase", "--autostash") not in calls:
            raise runner.subprocess.CalledProcessError(1, "git push")
        return ""
    return run_git, calls


def test_publish_commits_site_with_the_usual_message():
    run_git, calls = fake_git()
    assert runner.publish(runner.Step("after_race", 20, ""), "Mexico City Grand Prix", run_git)
    assert ("commit", "-m", "chore: add the Mexico City result to the site", "--", "site") in calls
    assert calls[-1] == ("push",)


def test_publish_names_a_prediction():
    run_git, calls = fake_git()
    runner.publish(runner.Step("predict", 20, ""), "São Paulo Grand Prix", run_git)
    assert ("commit", "-m", "chore: add the São Paulo prediction to the site", "--", "site") in calls


@pytest.mark.parametrize("branch, changed", [("feat/42-next-command", "M site/index.html"), ("main", "")])
def test_publish_skips_off_main_or_when_unchanged(branch, changed):
    run_git, calls = fake_git(branch, changed)
    assert not runner.publish(runner.Step("predict", 20, ""), "X Grand Prix", run_git)
    assert not any(c[0] in ("commit", "push") for c in calls)


def test_publish_rebases_when_main_moved():
    run_git, calls = fake_git(push_fails=True)
    assert runner.publish(runner.Step("after_race", 20, ""), "X Grand Prix", run_git)
    assert calls[-2:] == [("pull", "--rebase", "--autostash"), ("push",)]


def test_run_only_publishes_when_asked(calls, monkeypatch):
    published = []
    monkeypatch.setattr(runner, "publish", lambda step, name: published.append((step.action, name)))
    runner.run(2026, now=at("2026-11-08 21:00"))
    runner.run(2026, now=at("2026-11-07 18:30"), publish_site=True)
    assert published == []
    runner.run(2026, now=at("2026-11-08 21:00"), publish_site=True)
    assert published == [("after_race", "São Paulo Grand Prix")]


def test_log_appends_output(calls, tmp_path, monkeypatch):
    monkeypatch.setattr(runner.sys, "stdout", runner.sys.stdout)
    monkeypatch.setattr(runner.sys, "stderr", runner.sys.stderr)
    log = tmp_path / "next.log"
    runner.run(2026, now=at("2026-11-07 18:30"), log=str(log))
    runner.sys.stdout.close()
    assert "São Paulo Grand Prix qualifying is on" in log.read_text(encoding="utf-8")


@pytest.fixture
def toasts(monkeypatch):
    sent = []
    monkeypatch.setattr(runner.notify, "toast", lambda title, body: sent.append((title, body)))
    return sent


def test_notify_after_a_step(calls, toasts):
    runner.run(2026, now=at("2026-11-08 21:00"), notify_me=True)
    assert toasts == [("F1 Pred", "São Paulo Grand Prix scored.")]


def test_notify_stays_quiet_when_nothing_is_due(calls, toasts):
    runner.run(2026, now=at("2026-10-01"), notify_me=True)
    assert toasts == []


def test_notify_on_failure_and_reraise(calls, toasts, monkeypatch):
    def broken(season, event, wait_minutes, **grid):
        raise SystemExit("Qualifying for 2026 round 20 isn't available yet.")
    monkeypatch.setattr(runner.weekend, "run", broken)
    with pytest.raises(SystemExit):
        runner.run(2026, now=at("2026-11-07 20:00"), notify_me=True)
    assert toasts == [("F1 Pred: next failed", "Qualifying for 2026 round 20 isn't available yet.")]


def test_toast_is_skipped_off_windows(monkeypatch):
    monkeypatch.setattr(runner.notify.sys, "platform", "linux")
    runner.notify.toast("t", "b", run=lambda *a, **k: pytest.fail("should not run"))

"""Work out where the race weekend is and run whatever step is due."""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta, timezone

import pandas as pd

from f1pred import build, config, databranch, market, notify, predict, report, score, weekend
from f1pred.web import build as web

QUALI_LANDS = pd.Timedelta(hours=1)
RESULT_LANDS = pd.Timedelta(hours=3)
SESSIONS_MAX_AGE = pd.Timedelta(days=7)
MANILA = timezone(timedelta(hours=8))


@dataclass
class RoundFiles:
    grid_source: str | None = None
    pre_race: bool = False
    market: bool = False
    scored: bool = False


@dataclass
class Step:
    action: str
    rnd: int | None
    message: str
    name: str = ""


def manila(ts: pd.Timestamp) -> str:
    return ts.tz_convert(MANILA).strftime("%a %d %b %H:%M") + " Manila"


def _fastf1_sessions(year: int) -> pd.DataFrame:
    import fastf1

    from f1pred import fetch
    fetch.enable_cache()
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    rows = []
    for _, event in schedule[schedule["RoundNumber"] > 0].iterrows():
        times = {event.get(f"Session{i}"): event.get(f"Session{i}DateUtc") for i in range(1, 6)}
        if "Qualifying" in times and "Race" in times:
            rows.append({"RoundNumber": int(event["RoundNumber"]), "EventName": event["EventName"],
                         "QualiUTC": times["Qualifying"], "RaceUTC": times["Race"]})
    return pd.DataFrame(rows)


def sessions(year: int, loader: Callable[[int], pd.DataFrame] = _fastf1_sessions) -> pd.DataFrame:
    """Quali and race start per round, from a copy on disk refreshed weekly, or the copy when offline."""
    path = config.RAW_DIR / f"sessions_{year}.csv"
    fresh = path.exists() and pd.Timestamp.now() - pd.Timestamp.fromtimestamp(path.stat().st_mtime) < SESSIONS_MAX_AGE
    if fresh:
        out = pd.read_csv(path, encoding="utf-8")
    else:
        try:
            out = loader(year)
            path.parent.mkdir(parents=True, exist_ok=True)
            out.to_csv(path, index=False, encoding="utf-8")
        except Exception:
            if not path.exists():
                raise
            out = pd.read_csv(path, encoding="utf-8")
    for col in ("QualiUTC", "RaceUTC"):
        out[col] = pd.to_datetime(out[col], utc=True)
    return out.sort_values("RoundNumber").reset_index(drop=True)


def round_files(season: int, rnd: int, scored: set[tuple[int, int]]) -> RoundFiles:
    path = config.prediction_path(season, rnd, ".csv")
    files = RoundFiles(market=market.market_path(season, rnd).exists(), scored=(season, rnd) in scored)
    if path.exists():
        pred = pd.read_csv(path)
        files.grid_source = str(pred["GridSource"].iloc[0]) if "GridSource" in pred else ""
        files.pre_race = score.is_pre_race(pred)
    return files


def scored_rounds() -> set[tuple[int, int]]:
    path = config.PREDICTIONS_DIR / "scorecard.csv"
    if not path.exists():
        return set()
    card = pd.read_csv(path)
    return set(zip(card["Season"].astype(int), card["RoundNumber"].astype(int)))


def upcoming(sess: pd.DataFrame, now: pd.Timestamp) -> str:
    times = pd.concat([sess.assign(Session="qualifying", At=sess["QualiUTC"]),
                       sess.assign(Session="race", At=sess["RaceUTC"])])
    later = times[times["At"] > now].sort_values("At")
    if later.empty:
        return "No sessions left this season."
    nxt = later.iloc[0]
    return f"Next up: {nxt['EventName']} {nxt['Session']}, {manila(nxt['At'])}."


def plan(sess: pd.DataFrame, now: pd.Timestamp, files: Callable[[int], RoundFiles], fixes: bool = False) -> Step:
    started = sess[sess["QualiUTC"] <= now]
    if started.empty:
        return Step("wait", None, f"Nothing due. {upcoming(sess, now)}")
    race = started.iloc[-1]
    rnd, name = int(race["RoundNumber"]), race["EventName"]

    if now < race["RaceUTC"]:
        if now < race["QualiUTC"] + QUALI_LANDS:
            return Step("wait", rnd, f"{name} qualifying is on. Run again after {manila(race['QualiUTC'] + QUALI_LANDS)}.")
        f = files(rnd)
        if f.grid_source is None:
            return Step("predict", rnd, f"Predicting {name} from qualifying.", name)
        if fixes:
            return Step("regrid", rnd, f"Re-predicting {name} with your grid fixes.", name)
        if f.grid_source == "provisional":
            return Step("regrid", rnd, f"{name} was predicted on a provisional grid, checking for the official one.", name)
        return Step("wait", rnd, f"{name} is predicted. Race starts {manila(race['RaceUTC'])}.")

    if now < race["RaceUTC"] + RESULT_LANDS:
        return Step("wait", rnd, f"{name} race is on. Run again after {manila(race['RaceUTC'] + RESULT_LANDS)}.")
    f = files(rnd)
    if not f.market or (f.pre_race and not f.scored):
        return Step("after_race", rnd, f"{name} is over, saving market odds and scoring.", name)
    return Step("wait", rnd, f"Nothing due, {name} is scored. {upcoming(sess, now)}")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=config.PROJECT_ROOT, check=True, creationflags=databranch.NO_WINDOW,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def sync_main(run_git: Callable[..., str] = git) -> None:
    """Fast-forward main so site commits made by CI don't conflict with this run's."""
    if run_git("rev-parse", "--abbrev-ref", "HEAD") != "main":
        return
    try:
        run_git("pull", "--ff-only")
    except subprocess.CalledProcessError:
        print("Could not fast-forward main; carrying on with the local copy.")


def publish(step: Step, event_name: str, run_git: Callable[..., str] = git) -> bool:
    """Commit and push site/ on main; skip anywhere else so a feature branch never gets site commits."""
    branch = run_git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        print(f"Not publishing: on branch {branch}, not main.")
        return False
    if not run_git("status", "--porcelain", "--", "site"):
        print("Not publishing: site/ is unchanged.")
        return False
    what = "result" if step.action == "after_race" else "prediction"
    run_git("add", "--", "site")
    run_git("commit", "-m", f"chore: add the {event_name.removesuffix(' Grand Prix')} {what} to the site", "--", "site")
    try:
        run_git("push")
    except subprocess.CalledProcessError:
        run_git("pull", "--rebase", "--autostash")
        run_git("push")
    print("Published site/ to GitHub Pages.")
    return True


DONE_WORDS = {"predict": "predicted", "regrid": "re-predicted", "after_race": "scored"}


def run(season: int | None = None, wait_minutes: int = 0, now: pd.Timestamp | None = None,
        publish_site: bool = False, log: str | None = None, penalties: dict[str, int] | None = None,
        pitlane: list[str] | None = None, slots: dict[str, int] | None = None, notify_me: bool = False) -> Step:
    if log:
        sys.stdout = sys.stderr = open(log, "a", encoding="utf-8", buffering=1)
        print(f"\n[{pd.Timestamp.now():%Y-%m-%d %H:%M}]")
    try:
        step, published = _run(season, wait_minutes, now, publish_site, penalties, pitlane, slots)
    except (Exception, SystemExit) as exc:
        if notify_me:
            notify.toast("F1 Pred: next failed", str(exc) or type(exc).__name__)
        raise
    if notify_me and step.action != "wait":
        tail = ", site published" if published else ""
        notify.toast("F1 Pred", f"{step.name} {DONE_WORDS[step.action]}{tail}.")
    return step


def _run(season, wait_minutes, now, publish_site, penalties, pitlane, slots) -> tuple[Step, bool]:
    season = season or pd.Timestamp.now().year
    now = now or pd.Timestamp.now(tz="UTC")
    if publish_site:
        sync_main()
        databranch.pull()
    scored = scored_rounds()
    sess = sessions(season)
    fixes = bool(penalties or pitlane or slots)
    step = plan(sess, now, lambda rnd: round_files(season, rnd, scored), fixes)
    print(step.message)
    if fixes and step.action not in ("predict", "regrid"):
        print("Grid fixes not used: nothing is waiting to be predicted.")

    grid = {"penalties": penalties, "pitlane": pitlane, "slots": slots}
    if step.action != "wait" and not (config.PROCESSED_DIR / "entries.parquet").exists():
        build.run()
    if step.action == "predict":
        weekend.run(season, str(step.rnd), wait_minutes=wait_minutes, **grid)
    elif step.action == "regrid":
        predict.run(season, str(step.rnd), refresh=False, **grid)
        report.run(season, step.rnd)
        web.build_site()
    elif step.action == "after_race":
        if not market.market_path(season, step.rnd).exists():
            market.run(season, [step.rnd])
        if not score.run(season, refresh=True).empty:
            web.build_site()
    if publish_site:
        published = step.action != "wait" and publish(step, step.name)
        done = f" ({step.name} {DONE_WORDS[step.action]})" if step.name else ""
        databranch.push(f"chore: update data{done}")
        return step, published
    if step.action == "wait":
        return step, False
    print("\nDone. If site/ changed, commit and push it, or run with --publish.")
    return step, False

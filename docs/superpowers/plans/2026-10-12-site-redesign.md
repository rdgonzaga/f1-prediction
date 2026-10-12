# Site Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the string-built v1 site with a Jinja2-rendered, F1-broadcast-style site (home, races, race, drivers, driver, scorecard, how it works), and route `report` and `season` through the same templates.

**Architecture:** New package `src/f1pred/web/`. `data.py` turns saved predictions plus race results into plain dataclasses (no HTML). `charts.py` draws inline SVG. `build.py` owns a Jinja2 environment over `web/templates/`, writes every page as `<path>/index.html` under `site/`, copies `web/static/`, and renders standalone pages (CSS and JS inlined) for `report` and `season`. `site.py` and the HTML in `report.py` / `season.py` go away; their data helpers stay.

**Tech Stack:** Python 3.14, pandas, Jinja2 3.1.6, pytest, Playwright (screenshots only).

**Spec:** `docs/superpowers/specs/2026-10-12-site-redesign-design.md`

## Global Constraints

- Run Python as `.venv/Scripts/python.exe` (plain `python` is the Store alias). Tests: `.venv/Scripts/python.exe -m pytest -q`.
- Any Python file I/O uses `encoding="utf-8"`; site pages are written with `newline="\n"`.
- Dark only. Red accent `#e10600`. Titillium Web for text, JetBrains Mono for numbers (Google Fonts).
- Team colours come from `report.team_colors(team)[1]` (the dark-mode variant).
- Every page is `<path>/index.html`; links are relative (site lives under `/f1-prediction/`), directory links end in `/`. Standalone pages use `https://rdgonzaga.github.io/f1-prediction/` as the link root.
- Old v1 URLs (`2026/round-17.html`) are dropped, no redirects. `build_site` wipes `site/` before writing.
- Without JS every tab panel shows in order.
- `jinja2==3.1.6` pinned in `requirements.txt`.
- Commits: semantic subject line only, no trailers. Rainer is sole author.
- No em dashes in README, docs, PR text or site prose. (`—` as an empty table cell is fine.)

## Review Focus

1. Favourite retired, DSQ'd or missing from the result: verdict reads "Favourite RUS (78%) retired", no crash. Test in Task 1.
2. Old prediction CSV without `TeamName`, `PointsPct`, `DnfPct`, `DriverId`, `EventName`: page renders with grey colour, `—` cells, results' event name, abbreviation-matched driver id. Tests in Tasks 1 and 5.
3. Event or team names with `&` or `<`: escaped by Jinja autoescape and `html.escape` in SVG. Tests in Tasks 4 and 5.
4. Race winner absent from the prediction rows: winner still shown, card stripe uses the results' team. Test in Task 1.
5. Driver whose races are all retirements or pending: `places_off` is `None`, the chart draws with gaps, no crash. Tests in Tasks 3 and 4.

---

## File structure

| File | Responsibility |
|---|---|
| `src/f1pred/web/__init__.py` | empty package marker |
| `src/f1pred/web/data.py` | dataclasses `Row`, `Verdict`, `Race`, `NextRace`, `Scorecard`, `Season`, `Entry`, `Driver`, `Site`; builders `race`, `next_race`, `summary`, `scorecard`, `drivers`, `load` |
| `src/f1pred/web/charts.py` | `chance_bars`, `dumbbell`, `calibration`, `driver_season` (SVG strings) |
| `src/f1pred/web/build.py` | `environment`, `build_site`, `standalone_race`, `standalone_scorecard` |
| `src/f1pred/web/templates/*.html` | `base`, `home`, `races`, `race`, `drivers`, `driver`, `scorecard`, `how`, partials `_hero`, `_tower`, `_card` |
| `src/f1pred/web/static/site.css`, `site.js` | the look; tabs |
| `src/f1pred/report.py` | keeps team colours, `on_color`, `screenshot`, `run` |
| `src/f1pred/season.py` | keeps `season_data`, `podium_calibration`, `run` |
| delete `src/f1pred/site.py`, `tests/test_site.py` | |
| `pyproject.toml` | package data for templates/static |

Tests: `tests/test_web_data.py`, `tests/test_web_charts.py`, `tests/test_web_build.py`, rewritten `tests/test_report.py`, touched `tests/test_weekend.py`, `tests/test_score.py`.

---

### Task 1: Race data

**Files:**
- Modify: `requirements.txt` (add `jinja2==3.1.6` and `MarkupSafe==3.0.3` under a `# Website` heading)
- Create: `src/f1pred/web/__init__.py` (empty), `src/f1pred/web/data.py`
- Modify: `src/f1pred/report.py` (rename `_on_color` to `on_color`)
- Test: `tests/test_web_data.py`

**Interfaces:**
- Produces: `data.ordinal(n) -> str`; `data.Row` (fields `pos, code, driver_id, team, color, grid, win, podium, points, dnf, finish`; properties `grid_label, move, classified, gain, on_color`); `data.Verdict(favourite, podium_called, surprise)` with `.lines -> list[str]`; `data.Race` (fields `season, rnd, name, live, rows, verdict, winner, winner_color, made, notes, warnings`; properties `short_name, path, pending, favourite, podium, pick_hit, card_color`); `data.race(season, rnd, pred, actual, ids=None) -> Race`; `data.driver_ids(season_entries) -> dict[str, str]`.

- [ ] **Step 1: Write the failing tests** in `tests/test_web_data.py`

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_data.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'f1pred.web'`

- [ ] **Step 3: Implement**

`requirements.txt`, after the Data Visualization block:

```
# Website
jinja2==3.1.6
MarkupSafe==3.0.3
```

(Check the installed MarkupSafe with `.venv/Scripts/python.exe -m pip show markupsafe` and pin that exact version.)

`src/f1pred/report.py`: rename `_on_color` to `on_color` (definition and its one caller).

`src/f1pred/web/data.py`:

```python
"""Plain data for the site pages, built from saved predictions and race results."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from f1pred import report, score

MANILA_OFFSET = pd.Timedelta(hours=8)
PODIUM = {"1", "2", "3"}
NON_FINISH_WORDS = {"DNF": "retired", "DSQ": "was disqualified", "DNS": "did not start"}


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _num(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value)


@dataclass
class Row:
    pos: int
    code: str
    driver_id: str
    team: str
    color: str
    grid: float | None
    win: float
    podium: float
    points: float | None
    dnf: float | None
    finish: str | None = None

    @property
    def grid_label(self) -> str:
        if self.grid is None:
            return "—"
        return "PIT" if self.grid == 0 else str(int(self.grid))

    @property
    def move(self) -> int:
        """Places the prediction gains on the starting slot."""
        return int(self.grid) - self.pos if self.grid else 0

    @property
    def classified(self) -> bool:
        return self.finish is not None and self.finish.isdigit()

    @property
    def gain(self) -> int | None:
        """Places finished ahead of the predicted position."""
        return self.pos - int(self.finish) if self.classified else None

    @property
    def on_color(self) -> str:
        return report.on_color(self.color)


@dataclass
class Verdict:
    favourite: Row
    podium_called: int
    surprise: Row | None

    @property
    def lines(self) -> list[str]:
        fav = self.favourite
        if fav.finish == "1":
            first = f"{fav.code} won as favourite at {fav.win:.0f}%"
        else:
            how = (f"finished {ordinal(int(fav.finish))}" if fav.classified
                   else NON_FINISH_WORDS.get(fav.finish, "was not classified"))
            first = f"Favourite {fav.code} ({fav.win:.0f}%) {how}"
        lines = [first, f"{self.podium_called} of 3 podium spots called"]
        if self.surprise is not None:
            s = self.surprise
            lines.append(f"Biggest surprise: {s.code}, {ordinal(s.pos)} to {ordinal(int(s.finish))}")
        return lines


@dataclass
class Race:
    season: int
    rnd: int
    name: str
    live: bool
    rows: list[Row]
    verdict: Verdict | None = None
    winner: str | None = None
    winner_color: str | None = None
    made: str = ""
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def short_name(self) -> str:
        return self.name.removesuffix(" Grand Prix")

    @property
    def path(self) -> str:
        return f"{self.season}/round-{self.rnd:02d}/"

    @property
    def pending(self) -> bool:
        return self.verdict is None

    @property
    def favourite(self) -> Row:
        return max(self.rows, key=lambda r: r.win)

    @property
    def podium(self) -> list[Row]:
        return self.rows[:3]

    @property
    def pick_hit(self) -> bool:
        return self.winner is not None and self.winner == self.favourite.code

    @property
    def card_color(self) -> str:
        return self.winner_color or self.favourite.color


def _verdict(rows: list[Row], result: pd.Series) -> Verdict:
    on_podium = set(result[result.isin(PODIUM)].index)
    gainers = [r for r in rows if (r.gain or 0) > 0]
    surprise = max(gainers, key=lambda r: (r.gain, -int(r.finish)), default=None)
    return Verdict(max(rows, key=lambda r: r.win), sum(r.code in on_podium for r in rows[:3]), surprise)


def driver_ids(season_entries: pd.DataFrame) -> dict[str, str]:
    if "DriverId" not in season_entries:
        return {}
    known = season_entries.dropna(subset=["DriverId"])
    return dict(zip(known["Abbreviation"].astype(str), known["DriverId"].astype(str)))


def race(season: int, rnd: int, pred: pd.DataFrame, actual: pd.DataFrame,
         ids: dict[str, str] | None = None) -> Race:
    ids = ids or {}
    result = score.race_result(actual)
    rows = []
    for r in pred.sort_values("PredictedPosition").to_dict("records"):
        code, team = str(r["Abbreviation"]), _text(r.get("TeamName"))
        rows.append(Row(
            pos=int(r["PredictedPosition"]), code=code,
            driver_id=_text(r.get("DriverId")) or ids.get(code, code.lower()),
            team=team, color=report.team_colors(team)[1], grid=_num(r.get("Grid")),
            win=float(r["WinPct"]), podium=float(r["PodiumPct"]),
            points=_num(r.get("PointsPct")), dnf=_num(r.get("DnfPct")),
            finish=None if result is None else result.get(code)))

    first = pred.iloc[0]
    name = (_text(first.get("EventName"))
            or (_text(actual["EventName"].iloc[0]) if not actual.empty else "") or f"Round {rnd}")
    out = Race(season, rnd, name, score.is_pre_race(pred), rows)

    if result is not None:
        out.verdict = _verdict(rows, result)
        firsts = result[result == "1"]
        if not firsts.empty:
            out.winner = str(firsts.index[0])
            teams = actual.set_index("Abbreviation")["TeamName"] if "TeamName" in actual else pd.Series(dtype=str)
            team = next((r.team for r in rows if r.code == out.winner), None) or _text(teams.get(out.winner))
            out.winner_color = report.team_colors(team)[1]

    stamp = pd.to_datetime(first.get("PredictedAtUTC"), errors="coerce")
    if not pd.isna(stamp):
        out.made = f"{stamp:%a %d %b %Y, %H:%M} UTC · {stamp + MANILA_OFFSET:%H:%M} Manila"
    overrides = _text(first.get("GridOverrides")).strip()
    if overrides:
        out.notes.append(overrides)
    temperature = _num(first.get("Temperature"))
    if temperature is not None:
        races = _num(first.get("CalibrationRaces"))
        tail = f", calibrated on {int(races)} earlier races" if races is not None else ""
        out.notes.append(f"Probability spread {temperature:.2f}{tail}.")
    out.warnings = [w for w in _text(first.get("Warnings")).split("; ") if w.strip()]
    return out
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_data.py tests/test_report.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt src/f1pred/web src/f1pred/report.py tests/test_web_data.py
git commit -m "feat: add race data for the redesigned site"
```

---

### Task 2: Season, scorecard and next-race data

**Files:**
- Modify: `src/f1pred/web/data.py`
- Test: `tests/test_web_data.py`

**Interfaces:**
- Consumes: `data.race`, `data.driver_ids` (Task 1); `season.season_data(year) -> (races_df, drivers_df)` raising `SystemExit` when empty; `season.podium_calibration(drivers_df)`.
- Produces: `data.NextRace(rnd, name)` with `.short_name`; `data.fetch_schedule(year) -> pd.DataFrame`; `data.next_race(year, last_round, schedule) -> NextRace | None`; `data.summary(races_df) -> (heads: list[str], rows: list[dict])` where each row is `{"label": str, "cells": [{"model": str, "grid": str, "better": bool}, ...]}`; `data.Scorecard(races, calibration, heads, rows, beat, live_beat, live_count)`; `data.scorecard(year) -> Scorecard | None`; `data.Season(year, races, next_race=None, scorecard=None)` with `newest_first, latest, scored, picks_right, scorecard_path`; `data.Site(seasons, drivers)` with `current, scorecard_season`; `data.load(predictions, entries, schedule=fetch_schedule) -> Site`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_data.py`)

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_data.py -q`
Expected: FAIL, `AttributeError: module 'f1pred.web.data' has no attribute 'next_race'`

- [ ] **Step 3: Implement** (append to `data.py`; add `from collections.abc import Callable` and `from f1pred import season as season_scores` to the imports)

```python
SUMMARY_ROWS = [
    ("Spearman", "Order match", "{:.2f}"),
    ("WinnerHit", "Winner right", "{:.0%}"),
    ("PodiumHitRate", "Podium spots right", "{:.0%}"),
    ("MAE", "Places off, average", "{:.1f}"),
]


@dataclass
class NextRace:
    rnd: int
    name: str

    @property
    def short_name(self) -> str:
        return self.name.removesuffix(" Grand Prix")


def fetch_schedule(year: int) -> pd.DataFrame:
    import fastf1

    from f1pred import fetch
    fetch.enable_cache()
    return fastf1.get_event_schedule(year, include_testing=False)


def next_race(year: int, last_round: int, schedule: Callable[[int], pd.DataFrame] = fetch_schedule) -> NextRace | None:
    """The first scheduled round after the last prediction, or None when the lookup fails."""
    try:
        events = schedule(year)
        upcoming = events[events["RoundNumber"] > last_round].sort_values("RoundNumber")
    except Exception:
        return None
    if upcoming.empty:
        return None
    return NextRace(int(upcoming["RoundNumber"].iloc[0]), str(upcoming["EventName"].iloc[0]))


def summary(races: pd.DataFrame) -> tuple[list[str], list[dict]]:
    groups = [("All races", races), ("Live only", races[races["Live"]])]
    rows = []
    for metric, label, fmt in SUMMARY_ROWS:
        cells = []
        for _, g in groups:
            if g.empty:
                cells.append({"model": "—", "grid": "—", "better": False})
                continue
            model, grid = g[metric].mean(), g[f"Grid{metric}"].mean()
            better = model < grid if metric == "MAE" else model > grid
            cells.append({"model": fmt.format(model), "grid": fmt.format(grid), "better": bool(better)})
        rows.append({"label": label, "cells": cells})
    rows.append({"label": "Win chance given to the winner", "cells": [
        {"model": "—" if g.empty else f"{g['WinnerWinPct'].mean():.0f}%", "grid": "—", "better": False}
        for _, g in groups]})
    return [f"{name} ({len(g)})" for name, g in groups], rows


@dataclass
class Scorecard:
    races: pd.DataFrame
    calibration: pd.DataFrame
    heads: list[str]
    rows: list[dict]
    beat: int
    live_beat: int
    live_count: int


def scorecard(year: int) -> Scorecard | None:
    try:
        races, drivers_ = season_scores.season_data(year)
    except SystemExit:
        return None
    heads, rows = summary(races)
    live = races[races["Live"]]
    return Scorecard(races, season_scores.podium_calibration(drivers_), heads, rows,
                     beat=int((races["Spearman"] > races["GridSpearman"]).sum()),
                     live_beat=int((live["Spearman"] > live["GridSpearman"]).sum()), live_count=len(live))


@dataclass
class Season:
    year: int
    races: list[Race]
    next_race: NextRace | None = None
    scorecard: Scorecard | None = None

    @property
    def newest_first(self) -> list[Race]:
        return self.races[::-1]

    @property
    def latest(self) -> Race:
        return self.races[-1]

    @property
    def scored(self) -> list[Race]:
        return [r for r in self.races if not r.pending]

    @property
    def picks_right(self) -> int:
        return sum(r.pick_hit for r in self.scored)

    @property
    def scorecard_path(self) -> str:
        return f"{self.year}/scorecard/"


@dataclass
class Site:
    seasons: list[Season]
    drivers: list[Driver]

    @property
    def current(self) -> Season:
        return self.seasons[0]

    @property
    def scorecard_season(self) -> Season | None:
        return next((s for s in self.seasons if s.scorecard), None)


def load(predictions: list[tuple[int, int, pd.DataFrame]], entries: pd.DataFrame,
         schedule: Callable[[int], pd.DataFrame] = fetch_schedule) -> Site:
    seasons = []
    for year in sorted({s for s, _, _ in predictions}, reverse=True):
        season_entries = entries[entries["Season"] == year]
        ids = driver_ids(season_entries)
        races = [race(year, rnd, pred, season_entries[season_entries["RoundNumber"] == rnd], ids)
                 for s, rnd, pred in sorted(predictions, key=lambda p: p[1]) if s == year]
        seasons.append(Season(year, races, scorecard=scorecard(year)))
    seasons[0].next_race = next_race(seasons[0].year, seasons[0].latest.rnd, schedule)
    return Site(seasons, drivers(seasons))
```

Task 3 adds `Driver` and `drivers`; until then put a stub so this task's tests run:

```python
def drivers(seasons: list[Season]) -> list:
    return []
```

(Task 3 replaces it.)

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_data.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/f1pred/web/data.py tests/test_web_data.py
git commit -m "feat: add season, scorecard and next race data for the site"
```

---

### Task 3: Driver data

**Files:**
- Modify: `src/f1pred/web/data.py` (replace the `drivers` stub)
- Test: `tests/test_web_data.py`

**Interfaces:**
- Consumes: `Season`, `Race`, `Row` (Tasks 1-2).
- Produces: `data.display_name(driver_id) -> str`; `data.Entry(race, row)`; `data.Driver(driver_id, code, team, color, entries)` with `name, path, wins, podiums, favourite_races, favourite_scored, favourite_right, places_off, chart_entries`; `data.drivers(seasons) -> list[Driver]` sorted by `(team, name)`.

- [ ] **Step 1: Write the failing tests** (append)

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_data.py -q`
Expected: FAIL, `AttributeError: ... 'display_name'`

- [ ] **Step 3: Implement** (replace the stub)

```python
def display_name(driver_id: str) -> str:
    return driver_id.replace("_", " ").title()


@dataclass
class Entry:
    race: Race
    row: Row


@dataclass
class Driver:
    driver_id: str
    code: str
    team: str
    color: str
    entries: list[Entry] = field(default_factory=list)

    @property
    def name(self) -> str:
        return display_name(self.driver_id)

    @property
    def path(self) -> str:
        return f"drivers/{self.driver_id}/"

    @property
    def wins(self) -> int:
        return sum(e.row.finish == "1" for e in self.entries)

    @property
    def podiums(self) -> int:
        return sum(e.row.finish in PODIUM for e in self.entries)

    def _favourite(self, e: Entry) -> bool:
        return e.race.favourite.driver_id == self.driver_id

    @property
    def favourite_races(self) -> int:
        return sum(self._favourite(e) for e in self.entries)

    @property
    def favourite_scored(self) -> int:
        return sum(self._favourite(e) and not e.race.pending for e in self.entries)

    @property
    def favourite_right(self) -> int:
        return sum(self._favourite(e) and e.race.winner == e.row.code for e in self.entries)

    @property
    def places_off(self) -> float | None:
        gaps = [abs(e.row.gain) for e in self.entries if e.row.classified]
        return sum(gaps) / len(gaps) if gaps else None

    @property
    def chart_entries(self) -> list[Entry]:
        latest = self.entries[-1].race.season
        return [e for e in self.entries if e.race.season == latest]


def drivers(seasons: list[Season]) -> list[Driver]:
    by_id: dict[str, Driver] = {}
    for season_ in sorted(seasons, key=lambda s: s.year):
        for race_ in season_.races:
            for row in race_.rows:
                d = by_id.setdefault(row.driver_id, Driver(row.driver_id, row.code, row.team, row.color))
                d.code, d.team, d.color = row.code, row.team, row.color
                d.entries.append(Entry(race_, row))
    return sorted(by_id.values(), key=lambda d: (d.team, d.name))
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_data.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/f1pred/web/data.py tests/test_web_data.py
git commit -m "feat: add driver stats for the site"
```

---

### Task 4: Charts

**Files:**
- Create: `src/f1pred/web/charts.py`
- Test: `tests/test_web_charts.py`

**Interfaces:**
- Consumes: `data.Row`, `data.Entry`, `data.race`; scorecard frames from `season.season_data` / `podium_calibration`.
- Produces: `charts.chance_bars(rows: list[Row]) -> str`, `charts.dumbbell(races: pd.DataFrame) -> str`, `charts.calibration(cal: pd.DataFrame) -> str`, `charts.driver_season(entries: list[Entry], color: str) -> str`. All return `""` or an `<svg class="chart" ...>` string. SVG classes styled by `site.css`: `axis, code, val, label, gridline, live, link, model, gridpt, said, did, pred, act, dot`.

- [ ] **Step 1: Write the failing tests** in `tests/test_web_charts.py`

```python
import pandas as pd

from f1pred import season
from f1pred.web import charts, data
from test_score import actual_frame, pred_frame


def make_race(classified=("1", "2", "R", "3"), **pred_cols):
    return data.race(2026, 1, pred_frame(pre_race=True).assign(**pred_cols),
                     actual_frame().assign(Classified=list(classified)))


def test_chance_bars_draw_two_bars_per_driver():
    svg = charts.chance_bars(make_race().rows)
    assert svg.startswith('<svg class="chart"') and svg.endswith("</svg>")
    assert svg.count("<rect") == 8
    assert ">A</text>" in svg
    assert charts.chance_bars([]) == ""


def test_names_are_escaped():
    svg = charts.chance_bars(make_race(Abbreviation=["<X>", "B", "C", "D"]).rows)
    assert "&lt;X&gt;" in svg and "<X>" not in svg


def test_driver_season_leaves_gaps_for_retirements():
    finishes = [("1", "2", "R", "3"), ("2", "1", "R", "3"), ("R", "1", "2", "3"), ("3", "1", "2", "R")]
    entries = [data.Entry(r, r.rows[0]) for r in (make_race(c) for c in finishes)]
    svg = charts.driver_season(entries, "#ff8000")
    assert svg.count('class="pred"') == 1
    assert svg.count('class="act"') == 1
    assert svg.count('class="dot"') == 3


def test_driver_season_with_only_retirements_still_draws():
    entries = [data.Entry(r, r.rows[0]) for r in [make_race(("R", "1", "2", "3"))]]
    svg = charts.driver_season(entries, "#ff8000")
    assert 'class="act"' not in svg and 'class="pred"' in svg
    assert charts.driver_season([], "#ff8000") == ""


def test_scorecard_charts():
    races = pd.DataFrame({"RoundNumber": [1, 2], "EventName": ["Bahrain & Co Grand Prix", "Saudi Grand Prix"],
                          "Live": [False, True], "Spearman": [.8, .4], "GridSpearman": [.6, .5]})
    svg = charts.dumbbell(races)
    assert "Bahrain &amp; Co" in svg and svg.count(">LIVE<") == 1
    cal = season.podium_calibration(pd.DataFrame({"PodiumPct": [90.0, 90.0, 2.0], "OnPodium": [True, False, False]}))
    assert "n=2" in charts.calibration(cal)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_charts.py -q`
Expected: FAIL, `ImportError: cannot import name 'charts'`

- [ ] **Step 3: Implement** `src/f1pred/web/charts.py`

```python
"""Inline SVG charts for the site, styled by site.css."""
from __future__ import annotations

import html
import math

import pandas as pd

from f1pred.web.data import Entry, Row


def _open(label: str, width: int, height: float) -> str:
    return f'<svg class="chart" viewBox="0 0 {width} {height:.0f}" role="img" aria-label="{html.escape(label)}">'


def _vline(x: float, y1: float, y2: float) -> str:
    return f'<line class="gridline" x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y2}" />'


def chance_bars(rows: list[Row]) -> str:
    if not rows:
        return ""
    ceiling = max(max(r.podium for r in rows), max(r.win for r in rows))
    scale = max(20, math.ceil(ceiling / 20) * 20)
    width, row_h, pad_l, pad_r, head = 640, 28, 64, 48, 24
    plot = width - pad_l - pad_r
    height = head + row_h * len(rows)
    parts = [_open(f"Win and podium chance for the leading {len(rows)} drivers", width, height)]
    for step in range(5):
        x = pad_l + plot * step / 4
        parts.append(_vline(x, head - 6, height - 4))
        parts.append(f'<text class="axis" x="{x:.1f}" y="{head - 12}" text-anchor="middle">{scale * step // 4}</text>')
    for i, r in enumerate(rows):
        y = head + i * row_h
        podium, win = plot * min(r.podium, scale) / scale, plot * min(r.win, scale) / scale
        parts.append(f'<text class="axis" x="14" y="{y + 17}" text-anchor="end">{r.pos}</text>')
        parts.append(f'<text class="code" x="22" y="{y + 18}">{html.escape(r.code)}</text>')
        parts.append(f'<rect x="{pad_l}" y="{y + 4}" width="{podium:.1f}" height="16" fill="{r.color}" fill-opacity=".3" />')
        parts.append(f'<rect x="{pad_l}" y="{y + 4}" width="{win:.1f}" height="16" fill="{r.color}" />')
        parts.append(f'<text class="axis" x="{pad_l + podium + 6:.1f}" y="{y + 17}">{r.podium:.0f}</text>')
        if win >= 30:
            parts.append(f'<text class="val" x="{pad_l + win - 6:.1f}" y="{y + 17}" text-anchor="end" '
                         f'fill="{r.on_color}">{r.win:.0f}</text>')
    parts.append("</svg>")
    return "".join(parts)


def dumbbell(races: pd.DataFrame) -> str:
    width, row_h, pad_l, pad_r, head = 520, 30, 150, 44, 26
    plot = width - pad_l - pad_r
    lo = min(0.0, float(races[["Spearman", "GridSpearman"]].min().min()))
    height = head + row_h * len(races)

    def x(v: float) -> float:
        return pad_l + plot * (v - lo) / (1 - lo)

    parts = [_open("Order match per race, model against grid order", width, height)]
    for step in range(5):
        v = lo + (1 - lo) * step / 4
        parts.append(_vline(x(v), head - 6, height - 4))
        parts.append(f'<text class="axis" x="{x(v):.1f}" y="{head - 12}" text-anchor="middle">{v:.2f}</text>')
    for i, r in enumerate(races.itertuples(index=False)):
        y = head + i * row_h + 13
        name = html.escape(str(r.EventName).removesuffix(" Grand Prix"))
        tip = (f"R{r.RoundNumber} {name}: model {r.Spearman:.2f}, grid {r.GridSpearman:.2f}"
               f"{'' if r.Live else ' (made after the race)'}")
        parts.append(f"<g><title>{tip}</title>")
        parts.append(f'<text class="axis" x="22" y="{y + 4}" text-anchor="end">{r.RoundNumber}</text>')
        parts.append(f'<text class="label" x="30" y="{y + 5}">{name}</text>')
        parts.append(f'<line class="link" x1="{x(r.GridSpearman):.1f}" y1="{y}" x2="{x(r.Spearman):.1f}" y2="{y}" />')
        parts.append(f'<circle class="gridpt" cx="{x(r.GridSpearman):.1f}" cy="{y}" r="5" />')
        parts.append(f'<circle class="model" cx="{x(r.Spearman):.1f}" cy="{y}" r="5" />')
        if r.Live:
            parts.append(f'<text class="live" x="{width - 2}" y="{y + 4}" text-anchor="end">LIVE</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def calibration(cal: pd.DataFrame) -> str:
    width, row_h, pad_l, pad_r, head = 520, 42, 74, 56, 26
    plot = width - pad_l - pad_r
    height = head + row_h * len(cal)
    parts = [_open("Predicted podium chance against how often it happened", width, height)]
    for step in range(5):
        xv = pad_l + plot * step / 4
        parts.append(_vline(xv, head - 6, height - 4))
        parts.append(f'<text class="axis" x="{xv:.1f}" y="{head - 12}" text-anchor="middle">{step * 25}</text>')
    for i, (band, r) in enumerate(cal.iterrows()):
        y = head + i * row_h
        parts.append(f"<g><title>Said {band}: averaged {r.Said:.0f}%, happened {r.Did:.0f}% of {int(r.N)} times</title>")
        parts.append(f'<text class="axis" x="{pad_l - 10}" y="{y + 23}" text-anchor="end">{band}</text>')
        parts.append(f'<rect class="said" x="{pad_l}" y="{y + 4}" width="{plot * r.Said / 100:.1f}" height="14" />')
        parts.append(f'<rect class="did" x="{pad_l}" y="{y + 20}" width="{plot * r.Did / 100:.1f}" height="14" />')
        parts.append(f'<text class="axis" x="{pad_l + plot * max(r.Said, r.Did) / 100 + 8:.1f}" y="{y + 23}">'
                     f'n={int(r.N)}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def driver_season(entries: list[Entry], color: str) -> str:
    if not entries:
        return ""
    width, height, pad_l, pad_r, top, bottom = 640, 240, 36, 16, 12, 28
    plot_w, plot_h = width - pad_l - pad_r, height - top - bottom
    worst = max([20, *(e.row.pos for e in entries), *(int(e.row.finish) for e in entries if e.row.classified)])

    def x(i: int) -> float:
        return pad_l + (plot_w * i / (len(entries) - 1) if len(entries) > 1 else plot_w / 2)

    def y(p: int) -> float:
        return top + plot_h * (p - 1) / (worst - 1)

    parts = [_open("Predicted and actual finish by round", width, height)]
    for p in (1, 5, 10, 15, 20):
        parts.append(f'<line class="gridline" x1="{pad_l}" y1="{y(p):.1f}" x2="{width - pad_r}" y2="{y(p):.1f}" />')
        parts.append(f'<text class="axis" x="{pad_l - 8}" y="{y(p) + 4:.1f}" text-anchor="end">{p}</text>')
    for i, e in enumerate(entries):
        parts.append(f'<text class="axis" x="{x(i):.1f}" y="{height - 6}" text-anchor="middle">{e.race.rnd}</text>')
    predicted = " ".join(f"{x(i):.1f},{y(e.row.pos):.1f}" for i, e in enumerate(entries))
    parts.append(f'<polyline class="pred" points="{predicted}" />')
    segment: list[str] = []
    for i, e in enumerate([*entries, None]):
        if e is not None and e.row.classified:
            segment.append(f"{x(i):.1f},{y(int(e.row.finish)):.1f}")
            continue
        if len(segment) > 1:
            parts.append(f'<polyline class="act" stroke="{color}" points="{" ".join(segment)}" />')
        segment = []
    for i, e in enumerate(entries):
        if e.row.classified:
            tip = html.escape(f"R{e.race.rnd} {e.race.short_name}: predicted {e.row.pos}, finished {e.row.finish}")
            parts.append(f'<circle class="dot" cx="{x(i):.1f}" cy="{y(int(e.row.finish)):.1f}" r="4" '
                         f'fill="{color}"><title>{tip}</title></circle>')
    parts.append("</svg>")
    return "".join(parts)
```

Note `test_driver_season_leaves_gaps_for_retirements`: finishes 1, 2, DNF, 3 give one two-point `act` line (R1 to R2), a gap, and a lone dot for 3rd.

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_charts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/f1pred/web/charts.py tests/test_web_charts.py
git commit -m "feat: add svg charts for the redesigned site"
```

---

### Task 5: Templates, styles and the site build

**Files:**
- Create: `src/f1pred/web/build.py`, `src/f1pred/web/templates/{base,home,races,race,drivers,driver,scorecard,how,_hero,_tower,_card}.html`, `src/f1pred/web/static/site.css`, `src/f1pred/web/static/site.js`
- Modify: `pyproject.toml` (package data)
- Test: `tests/test_web_build.py`

**Interfaces:**
- Consumes: `data.load`, `data.fetch_schedule`, `data.ordinal`, `charts.*`, `score.load_predictions`, `build.load_processed`, `config.SITE_DIR`.
- Produces: `web.build.environment() -> jinja2.Environment`; `web.build.build_site(out_dir=None, schedule=data.fetch_schedule) -> Path`; `web.build.render_page(env, template, root, **context) -> str`; constants `SITE_URL`, `STATIC_DIR`. Template context: `root` (link prefix ending in `/`), `active` (nav key), `scorecard_path` (global, may be `None`), `inline_css` / `inline_js` (standalone only), plus `site`, `race`, `prev_race`, `next_race`, `season`, `driver` per page.

- [ ] **Step 1: Write the failing tests** in `tests/test_web_build.py`

```python
import re

import pandas as pd
import pytest

from f1pred import score
from f1pred.web import build as web
from test_score import actual_frame, pred_frame

IDS = ["alpha", "bravo", "charlie", "delta"]


@pytest.fixture
def built(tmp_path, monkeypatch):
    monkeypatch.setattr(score.config, "PREDICTIONS_DIR", tmp_path / "predictions")
    for rnd, pre_race in [(1, False), (2, True), (3, True)]:
        path = score.config.prediction_path(2026, rnd, ".csv")
        path.parent.mkdir(parents=True)
        pred_frame(pre_race=pre_race).assign(
            EventName=f"Race {rnd} & Co Grand Prix", TeamName="Ferrari", PointsPct=50.0, DnfPct=10.0,
            DriverId=IDS).to_csv(path, index=False)
    entries = pd.concat([actual_frame(rnd=1), actual_frame(rnd=2), actual_frame(rnd=3).assign(Classified="")],
                        ignore_index=True).assign(DriverId=IDS * 3)
    monkeypatch.setattr(score.build, "load_processed", lambda: (entries, None, None))
    out = tmp_path / "site"
    (out / "2026").mkdir(parents=True)
    (out / "2026" / "round-01.html").write_text("old", encoding="utf-8")
    return web.build_site(out, schedule=lambda year: pd.DataFrame(
        {"RoundNumber": [4], "EventName": ["Next Grand Prix"]}))


def read(root, rel):
    return (root / rel / "index.html").read_text(encoding="utf-8")


def test_every_page_is_written_and_old_pages_are_gone(built):
    pages = sorted(p.relative_to(built).as_posix() for p in built.rglob("*.html"))
    assert pages == [
        "2026/round-01/index.html", "2026/round-02/index.html", "2026/round-03/index.html",
        "2026/scorecard/index.html", "drivers/alpha/index.html", "drivers/bravo/index.html",
        "drivers/charlie/index.html", "drivers/delta/index.html", "drivers/index.html",
        "how-it-works/index.html", "index.html", "races/index.html"]
    assert (built / "static" / "site.css").exists() and (built / "static" / "site.js").exists()


def test_every_internal_link_resolves(built):
    for page in built.rglob("*.html"):
        for ref in re.findall(r'(?:href|src)="([^"]*)"', page.read_text(encoding="utf-8")):
            if ref.startswith(("http", "#")):
                continue
            target = page.parent / ref
            if ref.endswith("/") or ref in ("", "."):
                target = target / "index.html"
            assert target.resolve().exists(), f"{page.relative_to(built)} -> {ref}"


def test_pending_race_has_no_result_tab(built):
    pending = read(built, "2026/round-03")
    assert 'id="tab-result"' not in pending and "Result pending" in pending
    scored = read(built, "2026/round-02")
    assert 'id="tab-result"' in scored and ">DNF<" in scored
    assert "A won as favourite at 50%" in scored


def test_backfilled_race_is_labelled(built):
    assert "Made after the race" in read(built, "2026/round-01")
    live = read(built, "2026/round-02")
    assert "Made after the race" not in live and ">LIVE<" in live


def test_home_leads_with_the_latest_race_and_escapes_names(built):
    home = read(built, "")
    assert "Race 3 &amp; Co Grand Prix" in home and "Race 3 & Co" not in home
    assert "Next" in home and "2026/scorecard/" in home
    assert home.index("Race 3 &amp; Co") < home.index("Race 1 &amp; Co")


def test_driver_page_has_stats_and_log(built):
    page = read(built, "drivers/alpha")
    assert "Alpha" in page and "Races as favourite" in page
    assert page.count('href="../../2026/round-') >= 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_build.py -q`
Expected: FAIL, `ImportError: cannot import name 'build' from 'f1pred.web'`

- [ ] **Step 3: Implement `build.py`**

```python
"""Render the static site, and standalone pages, from saved predictions."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from f1pred import build as processed
from f1pred import config, score
from f1pred.web import charts, data

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
SITE_URL = "https://rdgonzaga.github.io/f1-prediction/"


def _pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def environment() -> Environment:
    env = Environment(loader=FileSystemLoader(WEB_DIR / "templates"), autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["pct"] = _pct
    env.globals.update(charts=charts, ordinal=data.ordinal, scorecard_path=None)
    return env


def render_page(env: Environment, template: str, root: str, **context) -> str:
    return env.get_template(template).render(root=root, **context)


def _write(out_dir: Path, rel: str, page: str) -> None:
    path = out_dir / rel / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8", newline="\n")


def build_site(out_dir: Path | None = None,
               schedule: Callable[[int], pd.DataFrame] = data.fetch_schedule) -> Path:
    out_dir = Path(out_dir or config.SITE_DIR)
    predictions = score.load_predictions()
    if not predictions:
        raise SystemExit(f"No saved predictions in {config.PREDICTIONS_DIR}")
    site = data.load(predictions, processed.load_processed()[0], schedule)
    env = environment()
    if site.scorecard_season:
        env.globals["scorecard_path"] = site.scorecard_season.scorecard_path

    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.copytree(STATIC_DIR, out_dir / "static")

    def page(rel: str, template: str, root: str, **context) -> None:
        _write(out_dir, rel, render_page(env, template, root, site=site, **context))

    page("", "home.html", "./", active="home")
    page("races", "races.html", "../", active="races")
    page("drivers", "drivers.html", "../", active="drivers")
    page("how-it-works", "how.html", "../", active="how")
    for season in site.seasons:
        races = season.races
        for i, race in enumerate(races):
            page(race.path, "race.html", "../../", active="races", race=race,
                 prev_race=races[i - 1] if i else None, next_race=races[i + 1] if i + 1 < len(races) else None)
        if season.scorecard:
            page(season.scorecard_path, "scorecard.html", "../../", active="scorecard", season=season)
    for driver in site.drivers:
        page(driver.path, "driver.html", "../../", active="drivers", driver=driver)
    count = sum(len(s.races) for s in site.seasons)
    print(f"Wrote the site to {out_dir} ({count} race pages, {len(site.drivers)} drivers). "
          f"Open index.html to check it.")
    return out_dir
```

`build_site` deletes `out_dir` before writing. `site/` only ever holds generated pages, so that is what clears the old v1 `round-NN.html` files.

- [ ] **Step 4: `pyproject.toml` package data**, so an installed (non-editable) package still finds templates:

```toml
[tool.setuptools.package-data]
"f1pred.web" = ["templates/*.html", "static/*"]
```

- [ ] **Step 5: `templates/base.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}F1 race predictions{% endblock %} · F1 Pred</title>
<meta name="description" content="F1 race predictions made after qualifying: finishing order plus win, podium, points and retirement chances.">
<script>document.documentElement.classList.add("js")</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Titillium+Web:wght@400;600;700;900&display=swap">
{% if inline_css %}
<style>{{ inline_css|safe }}</style>
{% else %}
<link rel="stylesheet" href="{{ root }}static/site.css">
{% endif %}
</head>
<body>
<header class="topbar">
  <div class="wrap topbar-inner">
    <a class="brand" href="{{ root }}"><span class="brand-mark"></span>F1<b>PRED</b></a>
    <nav class="mainnav" aria-label="Main">
      <a href="{{ root }}"{% if active == "home" %} aria-current="page"{% endif %}>Home</a>
      <a href="{{ root }}races/"{% if active == "races" %} aria-current="page"{% endif %}>Races</a>
      <a href="{{ root }}drivers/"{% if active == "drivers" %} aria-current="page"{% endif %}>Drivers</a>
      {% if scorecard_path %}
      <a href="{{ root }}{{ scorecard_path }}"{% if active == "scorecard" %} aria-current="page"{% endif %}>Scorecard</a>
      {% endif %}
      <a href="{{ root }}how-it-works/"{% if active == "how" %} aria-current="page"{% endif %}>How it works</a>
    </nav>
  </div>
</header>
<main class="wrap">
{% block content %}{% endblock %}
</main>
<footer class="wrap sitefoot">
  <p>Built from FastF1 timing data. Code and method on <a href="https://github.com/rdgonzaga/f1-prediction">GitHub</a>. Not affiliated with Formula 1.</p>
</footer>
{% if inline_js %}
<script>{{ inline_js|safe }}</script>
{% else %}
<script src="{{ root }}static/site.js"></script>
{% endif %}
</body>
</html>
```

- [ ] **Step 6: Partials**

`templates/_hero.html`:

```html
{% macro podium(race) %}
<section class="podium" aria-label="Predicted podium">
  {% for row in race.podium %}
  <div class="pod pod-{{ loop.index }}" style="--team: {{ row.color }}">
    <span class="pod-pos">P{{ loop.index }}</span>
    <span class="pod-code">{{ row.code }}</span>
    <span class="pod-team">{{ row.team or "Unknown team" }}</span>
    <span class="pod-win"><b>{{ row.win|pct(0) }}%</b> to win</span>
    {% if row.finish %}
    <span class="pod-fin">Finished {{ ordinal(row.finish|int) if row.classified else row.finish }}</span>
    {% endif %}
  </div>
  {% endfor %}
</section>
{% endmacro %}

{% macro verdict(race) %}
{% if race.pending %}
<p class="verdict pending">Result pending</p>
{% else %}
<p class="verdict">{% for line in race.verdict.lines %}<span>{{ line }}</span>{% endfor %}</p>
{% endif %}
{% endmacro %}
```

`templates/_tower.html`:

```html
{% macro driver_link(row, root) %}<a href="{{ root }}drivers/{{ row.driver_id }}/">{{ row.code }}</a>{% endmacro %}

{% macro tower(race, root) %}
<div class="scroller">
<table class="tower">
<thead><tr><th>Pred</th><th></th><th class="l">Driver</th><th>Win</th><th>Finish</th><th class="l"></th></tr></thead>
<tbody>
{% for row in race.rows %}
<tr>
  <td class="pos">{{ row.pos }}</td>
  <td class="stripe" style="--team: {{ row.color }}"><i></i></td>
  <td class="drv">{{ driver_link(row, root) }}<span class="drv-team">{{ row.team }}</span></td>
  <td class="num">{{ row.win|pct }}%</td>
  <td class="num fin">{% if row.classified %}{{ row.finish }}{% elif row.finish %}<span class="out">{{ row.finish }}</span>{% else %}—{% endif %}</td>
  <td class="l delta">
    {% if row.classified %}
      {% if row.gain == 0 %}<span class="hit" title="Exact">✓</span>
      {% elif row.gain > 0 %}<span class="up">▲{{ row.gain }}</span>
      {% else %}<span class="down">▼{{ -row.gain }}</span>{% endif %}
    {% endif %}
  </td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
{% endmacro %}

{% macro field_table(race, root) %}
<div class="scroller">
<table>
<thead><tr><th>Pred</th><th></th><th class="l">Driver</th><th class="l hide-sm">Team</th><th>Grid</th><th>Win</th><th>Podium</th><th>Points</th><th>DNF</th></tr></thead>
<tbody>
{% for row in race.rows %}
<tr>
  <td class="pos">{{ row.pos }}</td>
  <td class="stripe" style="--team: {{ row.color }}"><i></i></td>
  <td class="drv">{{ driver_link(row, root) }}</td>
  <td class="l team hide-sm">{{ row.team }}</td>
  <td class="num">{{ row.grid_label }}{% if row.move %}<span class="move">{{ "%+d"|format(row.move) }}</span>{% endif %}</td>
  <td class="num win">{{ row.win|pct }}</td>
  <td class="num">{{ row.podium|pct }}</td>
  <td class="num">{{ row.points|pct }}</td>
  <td class="num{% if row.dnf and row.dnf >= 20 %} risk{% endif %}">{{ row.dnf|pct }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
{% endmacro %}
```

`templates/_card.html`:

```html
{% macro race_card(race, root) %}
<a class="card" href="{{ root }}{{ race.path }}" style="--team: {{ race.card_color }}">
  <span class="card-top"><span>R{{ "%02d"|format(race.rnd) }}</span>{% if race.live %}<span class="badge-live">LIVE</span>{% endif %}</span>
  <span class="card-name">{{ race.short_name }}</span>
  <span class="card-line"><span class="lbl">Pick</span><b>{{ race.favourite.code }}</b><span class="num">{{ race.favourite.win|pct(0) }}%</span></span>
  <span class="card-line"><span class="lbl">Winner</span>
    {% if race.pending %}<span class="muted">pending</span>
    {% else %}<b>{{ race.winner or "—" }}</b>{% if race.pick_hit %}<span class="hit">✓</span>{% else %}<span class="miss">✗</span>{% endif %}
    {% endif %}
  </span>
</a>
{% endmacro %}

{% macro next_card(nxt) %}
<div class="card card-next">
  <span class="card-top"><span>R{{ "%02d"|format(nxt.rnd) }}</span><span>Next</span></span>
  <span class="card-name">{{ nxt.short_name }}</span>
  <span class="card-line"><span class="muted">Predicted after qualifying</span></span>
</div>
{% endmacro %}

{% macro season_cards(season, root, with_next=True) %}
<div class="cards">
  {% if with_next and season.next_race %}{{ next_card(season.next_race) }}{% endif %}
  {% for race in season.newest_first %}{{ race_card(race, root) }}{% endfor %}
</div>
{% endmacro %}
```

- [ ] **Step 7: Page templates**

`templates/home.html`:

```html
{% extends "base.html" %}
{% from "_hero.html" import podium, verdict %}
{% from "_card.html" import season_cards %}
{% block content %}
{% set race = site.current.latest %}
<section class="hero">
  <p class="eyebrow">{% if race.live %}<span class="badge-live">LIVE</span>{% endif %}<span>Latest · Round {{ race.rnd }} · {{ race.season }}</span></p>
  <h1><a href="{{ root }}{{ race.path }}">{{ race.name }}</a></h1>
  <p class="lede">Every race is predicted once qualifying is done: the likely podium, and each driver's chance to win. <a href="{{ root }}how-it-works/">How it works</a></p>
  {{ podium(race) }}
  {{ verdict(race) }}
  <p class="more"><a href="{{ root }}{{ race.path }}">Full timing tower →</a></p>
</section>

<h2 class="section-title">{{ site.current.year }} season</h2>
{{ season_cards(site.current, root) }}

{% set sc = site.scorecard_season %}
{% if sc %}
<section class="teaser">
  <p class="teaser-head"><span class="big">{{ sc.picks_right }}/{{ sc.scored|length }}</span> winners picked in {{ sc.year }}</p>
  <p>The model's order beat plain grid order in {{ sc.scorecard.beat }} of {{ sc.scorecard.races|length }} races. The percentages are what it adds.</p>
  <a class="btn" href="{{ root }}{{ sc.scorecard_path }}">Season scorecard →</a>
</section>
{% endif %}
{% endblock %}
```

`templates/races.html`:

```html
{% extends "base.html" %}
{% from "_card.html" import season_cards %}
{% block title %}Races{% endblock %}
{% block content %}
<h1>Races</h1>
<p class="lede">Every saved prediction, newest first. <span class="badge-live">LIVE</span> means it was made before the race; the rest were made afterwards, using only earlier races.</p>
{% for season in site.seasons %}
<h2 class="section-title">{{ season.year }}</h2>
{{ season_cards(season, root, with_next=loop.first) }}
{% endfor %}
{% endblock %}
```

`templates/race.html`:

```html
{% extends "base.html" %}
{% from "_hero.html" import podium, verdict %}
{% from "_tower.html" import tower, field_table %}
{% block title %}{{ race.name }} {{ race.season }}{% endblock %}
{% block content %}
<header class="race-head">
  <p class="eyebrow"><span>Round {{ race.rnd }} · {{ race.season }} season</span></p>
  <h1>{{ race.name }}</h1>
  <p class="race-meta">
    {% if race.live %}<span class="badge-live">LIVE</span><span>Predicted before the race</span>
    {% else %}<span class="badge-after">Made after the race</span>{% endif %}
    {% if race.made %}<span class="made">{{ race.made }}</span>{% endif %}
  </p>
</header>
{{ podium(race) }}
{{ verdict(race) }}

<div class="tabs" role="tablist" data-tabs>
  {% if not race.pending %}<button type="button" role="tab" aria-controls="tab-result">Result vs prediction</button>{% endif %}
  <button type="button" role="tab" aria-controls="tab-chances">Chances</button>
  <button type="button" role="tab" aria-controls="tab-field">Full field</button>
</div>
{% if not race.pending %}
<section class="panel" id="tab-result" role="tabpanel">
  <h2 class="section-title">Result vs prediction</h2>
  {{ tower(race, root) }}
</section>
{% endif %}
<section class="panel" id="tab-chances" role="tabpanel">
  <h2 class="section-title">Chances</h2>
  <p class="legend"><span><i></i>Win</span><span><i class="soft"></i>Podium</span></p>
  {{ charts.chance_bars(race.rows[:10])|safe }}
</section>
<section class="panel" id="tab-field" role="tabpanel">
  <h2 class="section-title">Full field</h2>
  {{ field_table(race, root) }}
</section>

{% if prev_race or next_race %}
<nav class="pager">
  {% if prev_race %}<a href="{{ root }}{{ prev_race.path }}">‹ R{{ prev_race.rnd }} {{ prev_race.short_name }}</a>{% else %}<span></span>{% endif %}
  {% if next_race %}<a href="{{ root }}{{ next_race.path }}">R{{ next_race.rnd }} {{ next_race.short_name }} ›</a>{% endif %}
</nav>
{% endif %}

<section class="note">
  <p>The predicted order sits close to the starting grid, and that is expected. This model has <strong>not</strong> been shown to beat "everyone finishes where they start". The percentages are what it adds: checked against past races, they come out about right on average.</p>
  <p>Grid penalties are only included if they were entered by hand. They are never in the timing data this is built from.</p>
</section>
{% if race.notes or race.warnings %}
<footer class="race-notes">
  {% for note in race.notes %}<p>{{ note }}</p>{% endfor %}
  {% for warning in race.warnings %}<p class="warn">Data check: {{ warning }}</p>{% endfor %}
</footer>
{% endif %}
{% endblock %}
```

`templates/drivers.html`:

```html
{% extends "base.html" %}
{% block title %}Drivers{% endblock %}
{% block content %}
<h1>Drivers</h1>
<p class="lede">Each driver's predictions against how their races went.</p>
<div class="teams">
{% for team, group in site.drivers|groupby("team") %}
  <section class="team-block" style="--team: {{ group[0].color }}">
    <h2>{{ team or "Unknown team" }}</h2>
    <ul class="driver-list">
      {% for d in group %}<li><a href="{{ root }}{{ d.path }}"><b>{{ d.code }}</b>{{ d.name }}</a></li>{% endfor %}
    </ul>
  </section>
{% endfor %}
</div>
{% endblock %}
```

`templates/driver.html`:

```html
{% extends "base.html" %}
{% block title %}{{ driver.name }}{% endblock %}
{% block content %}
<header class="driver-head" style="--team: {{ driver.color }}">
  <p class="eyebrow"><span>{{ driver.team or "Unknown team" }}</span></p>
  <h1>{{ driver.name }}</h1>
  <p class="driver-code">{{ driver.code }}</p>
</header>
<section class="stats">
  <div class="stat"><b>{{ driver.wins }}</b><span>Wins</span></div>
  <div class="stat"><b>{{ driver.podiums }}</b><span>Podiums</span></div>
  <div class="stat"><b>{{ driver.favourite_races }}</b><span>Races as favourite</span></div>
  <div class="stat"><b>{% if driver.favourite_scored %}{{ driver.favourite_right }}/{{ driver.favourite_scored }}{% else %}—{% endif %}</b><span>Favourite pick right</span></div>
  <div class="stat"><b>{% if driver.places_off is none %}—{% else %}{{ "%.1f"|format(driver.places_off) }}{% endif %}</b><span>Places off, average</span></div>
</section>

<h2 class="section-title">{{ driver.chart_entries[0].race.season }} season</h2>
<p class="legend" style="--team: {{ driver.color }}"><span><i class="line-pred"></i>Predicted</span><span><i class="line-act"></i>Finished</span><span>Gaps: retired or result pending</span></p>
{{ charts.driver_season(driver.chart_entries, driver.color)|safe }}

<h2 class="section-title">Race log</h2>
<div class="scroller">
<table>
<thead><tr><th>Rd</th><th class="l">Race</th><th class="l hide-sm">Team</th><th>Grid</th><th>Pred</th><th>Win</th><th>Finish</th></tr></thead>
<tbody>
{% for e in driver.entries|reverse %}
<tr>
  <td class="pos">{{ e.race.rnd }}</td>
  <td class="l"><a href="{{ root }}{{ e.race.path }}">{{ e.race.short_name }}</a>{% if e.race.live %} <span class="badge-live">LIVE</span>{% endif %}</td>
  <td class="l team hide-sm">{{ e.row.team }}</td>
  <td class="num">{{ e.row.grid_label }}</td>
  <td class="num">{{ e.row.pos }}</td>
  <td class="num">{{ e.row.win|pct }}%</td>
  <td class="num">{% if e.row.classified %}{{ e.row.finish }}{% elif e.row.finish %}<span class="out">{{ e.row.finish }}</span>{% else %}<span class="muted">pending</span>{% endif %}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
{% endblock %}
```

`templates/scorecard.html`:

```html
{% extends "base.html" %}
{% block title %}{{ season.year }} season scorecard{% endblock %}
{% block content %}
{% set card = season.scorecard %}
<header>
  <p class="eyebrow"><span>{{ season.year }} season · {{ card.races|length }} races scored</span></p>
  <h1>Season scorecard</h1>
</header>
<section class="teaser">
  <p class="teaser-head"><span class="big">{{ card.beat }}/{{ card.races|length }}</span> races where the model's order beat the grid's</p>
  <p>{% if card.live_count %}Live, before the race: <b>{{ card.live_beat }} of {{ card.live_count }}</b> beat grid order.{% else %}No live predictions scored yet.{% endif %}</p>
</section>

<h2 class="section-title">Totals</h2>
<div class="scroller">
<table class="totals">
<thead>
<tr><th></th>{% for head in card.heads %}<th colspan="2" class="c">{{ head }}</th>{% endfor %}</tr>
<tr><th></th>{% for head in card.heads %}<th>Model</th><th>Grid</th>{% endfor %}</tr>
</thead>
<tbody>
{% for row in card.rows %}
<tr><td class="l">{{ row.label }}</td>{% for c in row.cells %}<td class="num{% if c.better %} better{% endif %}">{{ c.model }}</td><td class="num">{{ c.grid }}</td>{% endfor %}</tr>
{% endfor %}
</tbody>
</table>
</div>

<h2 class="section-title">Race by race</h2>
<p class="legend"><span><i class="dot-model"></i>Model</span><span><i class="dot-grid"></i>Grid order</span><span>Order match, 1 is perfect</span></p>
{{ charts.dumbbell(card.races)|safe }}

<h2 class="section-title">Do the percentages hold up?</h2>
<p class="legend"><span><i class="said"></i>Podium chance it gave</span><span><i class="did"></i>How often it happened</span></p>
{{ charts.calibration(card.calibration)|safe }}

<section class="note">
  <p>Races marked <strong>LIVE</strong> were predicted after qualifying, before the race. The rest were made afterwards, but each one only used races that came before it.</p>
  <p>If the percentages are honest, the two bars in each band come out about the same length. Bands with few drivers in them bounce around, so read the small ones loosely.</p>
</section>
{% endblock %}
```

`templates/how.html` (adapted from the README, no em dashes):

```html
{% extends "base.html" %}
{% block title %}How it works{% endblock %}
{% block content %}
<h1>How it works</h1>
<div class="prose">
  <p class="lede">Each race is predicted once qualifying is done: the likely finishing order, and every driver's chance to win, reach the podium, score points or retire.</p>

  <h2>Is it any good?</h2>
  <p>Straight answer: it doesn't predict the finishing order any better than assuming everyone finishes where they started. That was tested across 48 races in 2024 and 2025, model against grid, race by race.</p>
  <p>The percentages are the real output, and a starting grid can't give you those. The grid tells you who starts first. It can't tell you he's 31% to win, or that someone has a 33% chance of not finishing. Checked against races that already happened, those numbers come out about right. The <a href="{{ root }}{{ scorecard_path or '' }}">season scorecard</a> tracks it race by race.</p>

  <h2>What goes in</h2>
  <p>Mostly the grid and qualifying: grid slot, pit-lane start, qualifying position, gap to pole, gap to teammate. On top of that, one pace estimate from practice lap times, recent finishes and the team's recent qualifying, for the fast car stuck at the back. It also knows the track: how well grid order has held there before and how often it brings out a safety car.</p>

  <h2>How the chances are made</h2>
  <p>A ranking model (XGBoost, pairwise) learns to order drivers within a race. Each race is then simulated 20,000 times from those scores, with the spread tuned on how the top three actually finished recently. A separate model estimates each driver's chance of retiring.</p>
  <p>Everything is walk-forward: a race is only ever predicted from races that happened before it.</p>

  <h2>Live, or made after the race</h2>
  <p>Races marked <span class="badge-live">LIVE</span> were real forecasts, made after qualifying and before lights out. The earlier 2026 races were filled in afterwards, still using only the races before them, so the season has a full record. Only live ones count as a real test.</p>

  <h2>Grid penalties</h2>
  <p>Penalties never appear in the timing data. They are entered by hand after qualifying, so a missed one means the model assumes that driver starts where they qualified.</p>

  <p>Code, tests and the full write-up are on <a href="https://github.com/rdgonzaga/f1-prediction">GitHub</a>.</p>
</div>
{% endblock %}
```

The scorecard link in `how.html` uses `scorecard_path or ''`; with no scorecard it points at the home page, which still resolves.

- [ ] **Step 8: `static/site.js`**

```js
document.querySelectorAll("[data-tabs]").forEach(function (list) {
  var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
  function show(tab) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
  }
  tabs.forEach(function (t) { t.addEventListener("click", function () { show(t); }); });
  if (tabs.length) show(tabs[0]);
});
```

- [ ] **Step 9: `static/site.css`**

```css
:root {
  --bg: #0a0a0d;
  --panel: #15151b;
  --panel-2: #1d1d26;
  --line: #2a2a34;
  --line-2: #3b3b48;
  --ink: #f4f4f6;
  --ink-2: #b8b8c4;
  --ink-3: #7d7d8b;
  --red: #e10600;
  --up: #34d27b;
  --down: #ff5a4e;
  --sans: "Titillium Web", ui-sans-serif, system-ui, "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "Cascadia Mono", monospace;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans); font-size: 16px; line-height: 1.5; }
a { color: inherit; }
.wrap { max-width: 1040px; margin: 0 auto; padding-left: 16px; padding-right: 16px; }
main.wrap { padding-top: 28px; padding-bottom: 56px; }
.num { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.muted { color: var(--ink-3); }

.topbar { background: #000; border-bottom: 3px solid var(--red); }
.topbar-inner { display: flex; align-items: center; gap: 24px; min-height: 54px; }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 900; font-size: 20px; letter-spacing: .02em; text-decoration: none; white-space: nowrap; }
.brand b { color: var(--red); font-weight: 900; }
.brand-mark { width: 14px; height: 14px; background: var(--red); transform: skewX(-20deg); }
.mainnav { display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none; }
.mainnav a { padding: 15px 10px 12px; font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-2); text-decoration: none; white-space: nowrap; border-bottom: 3px solid transparent; }
.mainnav a:hover { color: var(--ink); }
.mainnav a[aria-current="page"] { color: var(--ink); border-bottom-color: var(--ink); }

h1 { font-weight: 900; font-size: clamp(34px, 7vw, 58px); line-height: 1; text-transform: uppercase; letter-spacing: -.01em; margin: 8px 0 0; text-wrap: balance; }
h1 a { text-decoration: none; }
h1 a:hover { color: #fff; }
.section-title { display: flex; align-items: center; gap: 12px; margin: 44px 0 16px; font-weight: 700; font-size: 18px; text-transform: uppercase; letter-spacing: .06em; }
.section-title::before { content: ""; width: 4px; height: 18px; background: var(--red); }
.eyebrow { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 0; color: var(--ink-3); font-weight: 600; font-size: 13px; text-transform: uppercase; letter-spacing: .08em; }
.lede { color: var(--ink-2); max-width: 62ch; margin: 12px 0 0; }
.lede a, .more a, .prose a, .note a { color: var(--ink); text-decoration-color: var(--red); text-underline-offset: 3px; }
.badge-live { display: inline-block; background: var(--red); color: #fff; font-weight: 700; font-size: 11px; letter-spacing: .1em; line-height: 1.6; padding: 0 7px; border-radius: 2px; }
.badge-after { border: 1px solid var(--line-2); color: var(--ink-2); font-weight: 600; font-size: 12px; padding: 1px 8px; border-radius: 2px; }
.race-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: 14px 0 0; color: var(--ink-2); font-size: 14px; }
.made { color: var(--ink-3); font-family: var(--mono); font-size: 12px; }

.podium { display: grid; grid-template-columns: 1fr 1.25fr 1fr; grid-template-areas: "p2 p1 p3"; align-items: end; gap: 10px; margin-top: 24px; }
.pod { position: relative; display: flex; flex-direction: column; gap: 2px; padding: 14px 16px 16px; background: var(--panel); border-top: 4px solid var(--team); overflow: hidden; }
.pod::before { content: ""; position: absolute; inset: 0; background: linear-gradient(160deg, color-mix(in srgb, var(--team) 24%, transparent), transparent 62%); }
.pod > * { position: relative; }
.pod-1 { grid-area: p1; padding-block: 22px 24px; }
.pod-2 { grid-area: p2; }
.pod-3 { grid-area: p3; }
.pod-pos { font-family: var(--mono); font-weight: 700; font-size: 13px; color: var(--ink-3); }
.pod-code { font-weight: 900; font-size: 40px; line-height: 1; letter-spacing: .02em; }
.pod-1 .pod-code { font-size: 64px; }
.pod-team { color: var(--ink-2); font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pod-win { margin-top: 10px; color: var(--ink-2); font-size: 14px; }
.pod-win b { font-family: var(--mono); font-size: 22px; color: var(--ink); }
.pod-1 .pod-win b { font-size: 30px; }
.pod-fin { margin-top: 2px; color: var(--ink-3); font-size: 13px; }

.verdict { display: flex; flex-wrap: wrap; gap: 4px 0; margin: 12px 0 0; padding: 12px 16px; background: var(--panel); border-left: 4px solid var(--red); font-weight: 600; }
.verdict span + span::before { content: "·"; color: var(--ink-3); margin: 0 10px; }
.verdict.pending { color: var(--ink-2); border-left-color: var(--line-2); }
.more { margin: 14px 0 0; font-weight: 600; }

.tabs { display: none; gap: 2px; margin: 40px 0 0; border-bottom: 1px solid var(--line); overflow-x: auto; scrollbar-width: none; }
.js .tabs { display: flex; }
.tabs button { background: none; border: 0; border-bottom: 3px solid transparent; color: var(--ink-3); font: 700 14px var(--sans); text-transform: uppercase; letter-spacing: .06em; padding: 12px 14px 9px; cursor: pointer; white-space: nowrap; }
.tabs button:hover { color: var(--ink); }
.tabs button[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--red); }
.js .panel { margin-top: 20px; }
.js .panel > .section-title { display: none; }

.scroller { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 15px; }
th { padding: 0 10px 8px; border-bottom: 1px solid var(--line-2); color: var(--ink-3); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; text-align: right; white-space: nowrap; }
td { padding: 7px 10px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
th.l, td.l { text-align: left; }
th.c { text-align: center; }
tbody tr:nth-child(odd) { background: var(--panel); }
tbody tr:hover { background: var(--panel-2); }
td a { text-decoration: none; }
td a:hover { text-decoration: underline; text-decoration-color: var(--red); }
td.pos { width: 40px; color: var(--ink-3); font-family: var(--mono); }
td.stripe { width: 4px; padding: 0; }
td.stripe i { display: block; width: 4px; height: 24px; background: var(--team); }
td.drv { text-align: left; font-weight: 700; font-size: 17px; letter-spacing: .02em; }
.drv-team { display: block; color: var(--ink-3); font-weight: 400; font-size: 12px; letter-spacing: 0; line-height: 1.2; }
td.team { color: var(--ink-3); font-size: 14px; }
td.win { font-weight: 700; }
td.fin { font-weight: 700; }
.out { color: var(--down); font-family: var(--mono); font-weight: 700; font-size: 12px; letter-spacing: .04em; }
.hit { color: var(--up); font-weight: 700; margin-left: 6px; }
.miss { color: var(--ink-3); margin-left: 6px; }
td.delta .hit { margin-left: 0; }
.up { color: var(--up); font-family: var(--mono); font-size: 13px; }
.down { color: var(--down); font-family: var(--mono); font-size: 13px; }
.move { color: var(--ink-3); font-size: 12px; margin-left: 4px; }
.risk { color: var(--down); font-weight: 700; }
td.better { color: var(--up); font-weight: 700; }

.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.card { display: flex; flex-direction: column; gap: 4px; padding: 14px 16px 16px; background: var(--panel); border-top: 4px solid var(--team, var(--line-2)); text-decoration: none; transition: background 150ms ease; }
a.card:hover { background: var(--panel-2); }
.card-top { display: flex; align-items: center; gap: 8px; color: var(--ink-3); font-family: var(--mono); font-size: 12px; }
.card-name { margin-bottom: 8px; font-weight: 900; font-size: 22px; line-height: 1.1; text-transform: uppercase; }
.card-line { display: flex; align-items: baseline; gap: 8px; color: var(--ink-2); font-size: 14px; }
.card-line .lbl { width: 56px; flex: none; color: var(--ink-3); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
.card-line b { color: var(--ink); }
.card-next { opacity: .5; border-top-style: dashed; }

.teaser { display: grid; gap: 6px; margin-top: 44px; padding: 20px; background: var(--panel); border-left: 4px solid var(--red); }
.teaser p { margin: 0; color: var(--ink-2); }
.teaser-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; font-size: 20px; font-weight: 600; }
.big { color: var(--ink); font-family: var(--mono); font-weight: 700; font-size: 48px; line-height: 1; }
.btn { justify-self: start; margin-top: 10px; padding: 10px 16px; background: var(--red); color: #fff; font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: .06em; text-decoration: none; }
.btn:hover { background: #ff1e14; }

svg.chart { display: block; width: 100%; max-width: 720px; height: auto; }
svg .gridline { stroke: var(--line); stroke-width: 1; }
svg .axis { fill: var(--ink-3); font: 12px var(--mono); }
svg .code { fill: var(--ink); font: 700 16px var(--sans); }
svg .val { font: 700 12px var(--mono); }
svg .label { fill: var(--ink-2); font: 600 14px var(--sans); }
svg .live { fill: var(--red); font: 700 11px var(--mono); }
svg .link { stroke: var(--line-2); stroke-width: 2; }
svg .model { fill: var(--red); stroke: var(--bg); stroke-width: 2; }
svg .gridpt { fill: var(--bg); stroke: var(--ink-3); stroke-width: 2; }
svg .said { fill: var(--ink-3); fill-opacity: .45; }
svg .did { fill: var(--ink); }
svg .pred { fill: none; stroke: var(--ink-3); stroke-width: 2; stroke-dasharray: 4 4; }
svg .act { fill: none; stroke-width: 3; stroke-linejoin: round; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin: 0 0 12px; color: var(--ink-3); font-size: 13px; }
.legend i { display: inline-block; width: 18px; height: 10px; margin-right: 6px; vertical-align: middle; background: var(--ink-2); }
.legend i.soft { opacity: .3; }
.legend i.dot-model { width: 10px; border-radius: 50%; background: var(--red); }
.legend i.dot-grid { width: 10px; border-radius: 50%; background: none; border: 2px solid var(--ink-3); }
.legend i.said { background: var(--ink-3); opacity: .45; }
.legend i.did { background: var(--ink); }
.legend i.line-pred { height: 0; background: none; border-top: 2px dashed var(--ink-3); }
.legend i.line-act { height: 3px; background: var(--team, var(--ink)); }

.driver-head { padding: 24px 20px; background: linear-gradient(110deg, color-mix(in srgb, var(--team) 32%, var(--panel)), var(--panel) 70%); border-left: 6px solid var(--team); }
.driver-head .eyebrow { color: var(--ink-2); }
.driver-code { margin: 6px 0 0; color: var(--ink-2); font-family: var(--mono); font-weight: 700; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-top: 12px; }
.stat { padding: 14px 16px; background: var(--panel); }
.stat b { display: block; font-family: var(--mono); font-weight: 700; font-size: 28px; line-height: 1.2; }
.stat span { color: var(--ink-3); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
.teams { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin-top: 28px; }
.team-block { padding: 14px 16px; background: var(--panel); border-left: 4px solid var(--team); }
.team-block h2 { margin: 0 0 6px; font-size: 16px; text-transform: uppercase; letter-spacing: .06em; }
.driver-list { list-style: none; margin: 0; padding: 0; }
.driver-list a { display: flex; gap: 12px; padding: 5px 0; color: var(--ink-2); text-decoration: none; }
.driver-list a:hover { color: var(--ink); }
.driver-list b { width: 3.5ch; color: var(--ink); font-family: var(--mono); }

.prose { max-width: 66ch; }
.prose h2 { margin: 32px 0 8px; font-size: 20px; text-transform: uppercase; letter-spacing: .04em; }
.prose p { color: var(--ink-2); }
.note { max-width: 66ch; margin-top: 40px; color: var(--ink-2); font-size: 15px; }
.note strong { color: var(--ink); }
.pager { display: flex; justify-content: space-between; gap: 12px; margin-top: 32px; }
.pager a { color: var(--ink-2); font-weight: 600; text-decoration: none; }
.pager a:hover { color: var(--ink); }
.race-notes { margin-top: 24px; color: var(--ink-3); font-size: 13px; }
.race-notes p { margin: 0 0 4px; }
.race-notes .warn { color: var(--down); }
.sitefoot { padding-top: 18px; padding-bottom: 40px; border-top: 1px solid var(--line); color: var(--ink-3); font-size: 13px; }
.sitefoot a { color: var(--ink-2); }

@media (max-width: 640px) {
  .topbar-inner { flex-wrap: wrap; gap: 0; padding-top: 10px; }
  .mainnav { width: calc(100% + 20px); margin-left: -10px; }
  .mainnav a { padding: 10px; }
  .podium { grid-template-columns: 1fr 1fr; grid-template-areas: "p1 p1" "p2 p3"; }
  .pod-code { font-size: 30px; }
  .pod-1 .pod-code { font-size: 52px; }
  .verdict { flex-direction: column; }
  .verdict span + span::before { content: none; }
  .cards { grid-template-columns: 1fr 1fr; gap: 8px; }
  .card { padding: 12px; }
  .card-name { font-size: 17px; }
  .card-line .lbl { width: 46px; }
  td, th { padding-left: 6px; padding-right: 6px; }
  .hide-sm { display: none; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
```

- [ ] **Step 10: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web_build.py -q`
Expected: PASS. If the link test fails on `href="./"` from home, the `ref in ("", ".")` / trailing-slash branch already covers it; check the failing ref.

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml src/f1pred/web tests/test_web_build.py
git commit -m "feat: render the redesigned site with jinja templates"
```

---

### Task 6: Standalone report and season pages through the templates

**Files:**
- Modify: `src/f1pred/web/build.py` (add `standalone_race`, `standalone_scorecard`)
- Modify: `src/f1pred/report.py` (drop `STYLE`, `CHART_ROWS`, `MANILA_OFFSET`, `render`, `_chart`, `_table`, `_result_cell`, `_footer`, `_move`, `_grid_label`, `_pct`, `_cell`, `_team_style`, `_season_round`, `standalone`; keep `TEAM_COLORS`, `FALLBACK_COLOR`, colour helpers, `team_colors`, `on_color`, `screenshot`, `run`)
- Modify: `src/f1pred/season.py` (drop `SEASON_STYLE`, `SUMMARY_ROWS`, `_summary`, `_dumbbell`, `_calibration`, `render`, the `html` import and the `report` import; keep `PODIUM_BINS`, `season_data`, `podium_calibration`, `run`)
- Test: `tests/test_report.py` (rewrite), `tests/test_season.py` (unchanged, must still pass)

**Interfaces:**
- Consumes: `data.race`, `data.driver_ids`, `data.scorecard`, `data.Season`, `environment`, `render_page`, `STATIC_DIR`, `SITE_URL`.
- Produces: `web.build.standalone_race(season, rnd) -> str`; `web.build.standalone_scorecard(season) -> str` (raises `SystemExit` when nothing is scored); `report.screenshot(html_path, width=SCREENSHOT_WIDTH, out=None) -> Path | None` (writes to `out` or `html_path.with_suffix(".png")`).

- [ ] **Step 1: Rewrite `tests/test_report.py`**

```python
import sys

import pandas as pd
import pytest

from f1pred import report, score
from test_score import actual_frame, pred_frame


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(score.config, "PREDICTIONS_DIR", tmp_path)
    path = score.config.prediction_path(2026, 15, ".csv")
    path.parent.mkdir(parents=True)
    pred_frame(pre_race=True).assign(EventName="Azerbaijan Grand Prix", TeamName="Mercedes",
                                     GridOverrides="Grid overrides: VER +5").to_csv(path, index=False)
    entries = actual_frame(rnd=15).assign(Classified="")
    monkeypatch.setattr(score.build, "load_processed", lambda: (entries, None, None))
    shots = []
    monkeypatch.setattr(report, "screenshot", lambda html_path, **kw: shots.append(html_path) or None)
    return shots


def test_run_writes_a_standalone_page_and_asks_for_a_png(saved):
    path = report.run(2026, 15)
    page = path.read_text(encoding="utf-8")
    assert path.name == "2026_R15.html" and saved == [path]
    assert page.startswith("<!doctype html>") and page.rstrip().endswith("</html>")
    assert "<style>" in page and "static/site.css" not in page and "static/site.js" not in page
    assert 'href="https://rdgonzaga.github.io/f1-prediction/races/"' in page
    assert "Azerbaijan Grand Prix" in page and "Predicted before the race" in page
    assert "VER +5" in page and "Result pending" in page


def test_missing_prediction_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(report.config, "PREDICTIONS_DIR", tmp_path)
    with pytest.raises(SystemExit):
        report.run(2026, 99)


def test_team_colours_stay_visible_on_dark():
    light, dark = report.team_colors("Red Bull Racing")
    assert dark != light
    assert report.team_colors("Nobody")[1] == report.team_colors("")[1]


def test_png_is_skipped_without_playwright(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    assert report.screenshot(tmp_path / "page.html") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report.py tests/test_season.py -q`
Expected: `test_run_writes_a_standalone_page...` FAILS (old page has no top bar link to `races/`).

- [ ] **Step 3: Add standalone renderers to `web/build.py`**

```python
def _standalone(template: str, scorecard_path: str, **context) -> str:
    env = environment()
    env.globals["scorecard_path"] = scorecard_path
    return render_page(env, template, SITE_URL,
                       inline_css=(STATIC_DIR / "site.css").read_text(encoding="utf-8"),
                       inline_js=(STATIC_DIR / "site.js").read_text(encoding="utf-8"), **context)


def standalone_race(season: int, rnd: int) -> str:
    """One race page with CSS and JS inlined, linking back to the live site."""
    pred = pd.read_csv(config.prediction_path(season, rnd, ".csv"))
    entries = processed.load_processed()[0]
    season_entries = entries[entries["Season"] == season]
    race = data.race(season, rnd, pred, season_entries[season_entries["RoundNumber"] == rnd],
                     data.driver_ids(season_entries))
    return _standalone("race.html", f"{season}/scorecard/", active="races", race=race,
                       prev_race=None, next_race=None)


def standalone_scorecard(season: int) -> str:
    card = data.scorecard(season)
    if card is None:
        raise SystemExit(f"No scored predictions for {season} yet.")
    return _standalone("scorecard.html", f"{season}/scorecard/", active="scorecard",
                       season=data.Season(season, [], scorecard=card))
```

- [ ] **Step 4: Rewrite `report.run` and `screenshot`**

```python
def screenshot(html_path: Path, width: int = SCREENSHOT_WIDTH, out: Path | None = None) -> Path | None:
    ...  # body unchanged except:
    png_path = Path(out) if out else html_path.with_suffix(".png")


def run(season: int, rnd: int, png: bool = True) -> Path:
    from f1pred.web import build as web
    csv_path = config.prediction_path(season, rnd, ".csv")
    if not csv_path.exists():
        raise SystemExit(f"No saved prediction at {csv_path}; run `predict` first.")
    out_path = csv_path.with_suffix(".html")
    out_path.write_text(web.standalone_race(season, rnd), encoding="utf-8", newline="\n")
    print(f"Wrote {out_path}\nOpen it in a browser, or send the path to Claude to publish a shareable link.")
    png_path = screenshot(out_path) if png else None
    if png_path:
        print(f"Wrote {png_path}, ready to send as a picture.")
    return out_path
```

Then delete everything listed under "drop" above from `report.py`, plus the now unused `html`, `math` and `pandas` imports. Update the module docstring to `"""Team colours, the shareable race page and its PNG."""`.

- [ ] **Step 5: Rewrite `season.run`**

```python
def run(season: int, png: bool = True):
    from f1pred.web import build as web
    out_path = config.PREDICTIONS_DIR / str(season) / f"{season}_season.html"
    out_path.write_text(web.standalone_scorecard(season), encoding="utf-8", newline="\n")
    print(f"Wrote {out_path}")
    png_path = screenshot(out_path) if png else None
    if png_path:
        print(f"Wrote {png_path}, ready to send as a picture.")
    return out_path
```

Import line becomes `from f1pred.report import screenshot`. Drop everything listed under "drop" above.

- [ ] **Step 6: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report.py tests/test_season.py tests/test_web_build.py -q`
Expected: PASS (`test_season.test_run_writes_page_with_live_races_marked` still finds "LIVE" and "2/2").

- [ ] **Step 7: Commit**

```bash
git add src/f1pred/report.py src/f1pred/season.py src/f1pred/web/build.py tests/test_report.py
git commit -m "refactor: render report and season pages through the site templates"
```

---

### Task 7: Switch callers to the new site and remove site.py

**Files:**
- Modify: `src/f1pred/__main__.py`, `src/f1pred/weekend.py`
- Delete: `src/f1pred/site.py`, `tests/test_site.py`
- Modify: `tests/test_weekend.py`, `tests/test_score.py`

**Interfaces:**
- Consumes: `web.build.build_site()`.

- [ ] **Step 1: Update tests first**

`tests/test_weekend.py`: change `monkeypatch.setattr(weekend.site, "build_site", ...)` to `monkeypatch.setattr(weekend.web, "build_site", ...)`.

`tests/test_score.py`: move `test_race_result_labels` over from `test_site.py`:

```python
def test_race_result_labels():
    result = score.race_result(actual_frame().assign(Classified=["1", "W", "D", "R"]))
    assert list(result) == ["1", "DNS", "DSQ", "DNF"]
    assert score.race_result(actual_frame().assign(Classified="")) is None
```

Then `git rm tests/test_site.py`.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_weekend.py -q`
Expected: FAIL, `AttributeError: module 'f1pred.weekend' has no attribute 'web'`

- [ ] **Step 3: Implement**

`weekend.py`: `from f1pred import build, fetch, predict, report` plus `from f1pred.web import build as web`; replace `site.build_site()` with `web.build_site()`.

`__main__.py`: in `score` and `site` commands replace `from f1pred import ... site` / `site.build_site()` with `from f1pred.web import build as web` / `web.build_site()`.

`git rm src/f1pred/site.py`. Grep that nothing else imports it: `grep -rn "f1pred import.*site\|site\.build_site" src tests` returns nothing.

- [ ] **Step 4: Full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A src/f1pred tests
git commit -m "refactor: build the site from the web package and drop site.py"
```

---

### Task 8: README, screenshots, rebuild and PR

**Files:**
- Modify: `README.md` (website section, layout block)
- Regenerate: `site/`

- [ ] **Step 1: README.** In "## The website" describe the pages in one short paragraph (latest race up top, race archive, a page per driver, scorecard, how it works) and keep the commit-and-push routine. In "## Layout" add `web/` (site data, charts, Jinja templates, CSS). No em dashes.

- [ ] **Step 2: Screenshots.** Build to a scratch folder and shoot at both widths:

```bash
.venv/Scripts/python.exe - <<'EOF'
from pathlib import Path
from f1pred import report
from f1pred.web import build as web
out = Path(r"C:\Users\rdgonzaga\.claude\jobs\bfb37851\tmp\site")
web.build_site(out)
shots = out.parent / "shots"; shots.mkdir(exist_ok=True)
pages = {"home": "", "r15": "2026/round-15", "r05": "2026/round-05",
         "antonelli": "drivers/antonelli", "scorecard": "2026/scorecard"}
for name, rel in pages.items():
    for width in (1280, 390):
        report.screenshot(out / rel / "index.html", width=width, out=shots / f"{name}-{width}.png")
EOF
```

Look at every PNG, fix anything broken, then show Rainer. **Stop here for the go/no-go.** If he says it looks bad, the plan changes to the JSON + JS frontend.

- [ ] **Step 3: Rebuild the real site** with `.venv/Scripts/python.exe -m f1pred site`, check `git status site/` shows the new tree and the old `round-NN.html` files deleted.

- [ ] **Step 4: Full test run** `.venv/Scripts/python.exe -m pytest -q`.

- [ ] **Step 5: Commit and push**

```bash
git add README.md site
git commit -m "chore: rebuild the site with the redesign"
git push
```

- [ ] **Step 6: PR** with `gh pr create --base main --title "feat: redesign the site" --body ...`. Body: short, plain, no em dashes, ends with `Closes #32`. No Claude trailers.

- [ ] **Step 7: Wait for CI** (`gh pr checks --watch`), then tick the boxes on issue #32 (`gh issue view 32`, edit the body). Hand Rainer `! gh pr merge <N> --squash --delete-branch`.

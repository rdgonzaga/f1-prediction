"""Plain data for the site pages, built from saved predictions and race results."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from f1pred import report, score
from f1pred import season as season_scores

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

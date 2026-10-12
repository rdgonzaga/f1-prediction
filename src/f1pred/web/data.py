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

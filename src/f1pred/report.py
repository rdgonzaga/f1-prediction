"""Standalone HTML page for a saved prediction."""
from __future__ import annotations

import html
import math
from pathlib import Path

import pandas as pd

from f1pred import config

PREDICTIONS_DIR = config.PROCESSED_DIR / "predictions"
CHART_ROWS = 10
MANILA_OFFSET = pd.Timedelta(hours=8)

# Constructor colours as published by FastF1 for 2026.
TEAM_COLORS = {
    "Alpine": "#ff87bc",
    "Aston Martin": "#00665f",
    "Audi": "#ff2d00",
    "Cadillac": "#444444",
    "Ferrari": "#e80020",
    "Haas F1 Team": "#b6babd",
    "McLaren": "#ff8000",
    "Mercedes": "#27f4d2",
    "Racing Bulls": "#fcd700",
    "Red Bull Racing": "#0600ef",
    "Williams": "#00a0dd",
}
FALLBACK_COLOR = "#8a8a8a"

STYLE = """
:root {
  --bg: #f4f3ef;
  --panel: #fbfaf7;
  --ink: #16160f;
  --ink-2: #4c4b44;
  --ink-3: #85837a;
  --rule: #ddd9cf;
  --rule-strong: #bdb8aa;
  --signal: #b4341f;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0b0d10;
    --panel: #12151a;
    --ink: #eef1f4;
    --ink-2: #a8b0b8;
    --ink-3: #6f7880;
    --rule: #222831;
    --rule-strong: #39424e;
    --signal: #ff5c3d;
    color-scheme: dark;
  }
  :root:not([data-theme="light"]) .mark,
  :root:not([data-theme="light"]) .bar { background: var(--team-d); }
  :root:not([data-theme="light"]) rect.bar { fill: var(--team-d); background: none; }
  :root:not([data-theme="light"]) rect.bar-soft { fill: var(--team-d); }
}
:root[data-theme="dark"] {
  --bg: #0b0d10;
  --panel: #12151a;
  --ink: #eef1f4;
  --ink-2: #a8b0b8;
  --ink-3: #6f7880;
  --rule: #222831;
  --rule-strong: #39424e;
  --signal: #ff5c3d;
  color-scheme: dark;
}
:root[data-theme="dark"] .mark,
:root[data-theme="dark"] .bar { background: var(--team-d); }
:root[data-theme="dark"] rect.bar { fill: var(--team-d); background: none; }
:root[data-theme="dark"] rect.bar-soft { fill: var(--team-d); }

* { box-sizing: border-box; }
body {
  margin: 0;
  padding-block: 28px 64px;
  padding-left: 16px;
  padding-right: 16px;
  background: var(--bg);
  color: var(--ink);
  font-family: "Barlow", ui-sans-serif, system-ui, "Segoe UI", sans-serif;
  font-size: 16px;
  line-height: 1.5;
}
.wrap { max-width: 880px; margin: 0 auto; }
.num { font-family: "IBM Plex Mono", ui-monospace, "Cascadia Mono", monospace; font-variant-numeric: tabular-nums; }
.cond { font-family: "Barlow Condensed", "Barlow", ui-sans-serif, sans-serif; }

.meta { display: flex; gap: 10px; align-items: baseline; color: var(--ink-3); font-size: 14px; }
.meta .rnd { color: var(--ink-2); font-weight: 600; }
h1 {
  font-family: "Barlow Condensed", "Barlow", ui-sans-serif, sans-serif;
  font-size: clamp(38px, 9vw, 62px); font-weight: 700; letter-spacing: -.01em; line-height: .96;
  margin: 4px 0 0; text-transform: uppercase; text-wrap: balance;
}
.stamp { color: var(--ink-3); font-size: 13px; margin: 10px 0 0; }
.tag {
  display: inline-flex; align-items: center; gap: 8px; margin-top: 14px;
  border: 1px solid var(--rule-strong); border-radius: 2px; padding: 4px 10px;
  font-size: 13px; font-weight: 600; color: var(--ink-2);
}
.tag i { width: 8px; height: 8px; background: var(--signal); display: block; }
.tag.after { color: var(--signal); border-color: var(--signal); }

.rule { border: 0; border-top: 1px solid var(--rule); margin: 26px 0 0; }
.rule.heavy { border-top: 2px solid var(--ink); }
h2 {
  font-family: "Barlow Condensed", "Barlow", ui-sans-serif, sans-serif;
  font-size: 20px; font-weight: 600; text-transform: uppercase; letter-spacing: .01em;
  color: var(--ink-2); margin: 18px 0 12px;
}

.headline { display: flex; flex-wrap: wrap; align-items: last baseline; gap: 6px 18px; margin-top: 18px; }
.headline .code {
  font-family: "Barlow Condensed", "Barlow", ui-sans-serif, sans-serif;
  font-size: clamp(52px, 14vw, 92px); font-weight: 700; line-height: .86; letter-spacing: -.02em;
}
.headline .pct { font-size: clamp(22px, 5vw, 30px); font-weight: 500; color: var(--ink-2); }
.headline .sub { flex-basis: 100%; color: var(--ink-3); font-size: 15px; margin-top: 4px; }
.headline .sub b { color: var(--ink-2); font-weight: 600; }

.legend { display: flex; gap: 16px; font-size: 13px; color: var(--ink-3); margin: 0 0 10px; }
.legend i { display: inline-block; width: 22px; height: 9px; vertical-align: middle; margin-right: 6px;
  background: var(--ink-3); }
.legend i.soft { opacity: .3; }
svg { width: 100%; height: auto; display: block; }
rect.bar { fill: var(--team-l); }
rect.bar-soft { fill: var(--team-l); fill-opacity: .28; }

.scroller { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 15px; }
thead th {
  font-family: "Barlow Condensed", "Barlow", ui-sans-serif, sans-serif;
  font-size: 14px; font-weight: 600; text-transform: uppercase; color: var(--ink-3);
  text-align: right; padding: 0 8px 6px; white-space: nowrap; border-bottom: 1px solid var(--rule-strong);
}
thead th.left { text-align: left; }
tbody tr { border-bottom: 1px solid var(--rule); transition: background 160ms ease; }
tbody tr:hover { background: var(--panel); }
td { padding: 6px 8px; text-align: right; white-space: nowrap; }
td.pos { color: var(--ink-3); text-align: right; width: 30px; padding-right: 2px; }
td.mark-cell { width: 4px; padding: 0 0 0 6px; }
.mark { display: block; width: 4px; height: 20px; background: var(--team-l); }
td.drv {
  font-family: "Barlow Condensed", "Barlow", ui-sans-serif, sans-serif;
  font-size: 19px; font-weight: 600; text-align: left; padding-left: 8px;
}
td.team { text-align: left; color: var(--ink-3); font-size: 14px; }
td.win { font-weight: 600; }
.move { color: var(--ink-3); font-size: 13px; margin-left: 4px; }
.move.up { color: var(--signal); }
.risk { color: var(--signal); font-weight: 600; }

.note { margin-top: 14px; max-width: 62ch; }
.note p { margin: 0 0 12px; color: var(--ink-2); font-size: 15px; }
.note p:last-child { margin-bottom: 0; }
.note strong { color: var(--ink); }
footer { margin-top: 26px; color: var(--ink-3); font-size: 13px; }
footer p { margin: 0 0 5px; }
footer .warn { color: var(--signal); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
@media (max-width: 460px) {
  td.team, thead th.team { display: none; }
}
"""


def _season_round(csv_path: Path) -> tuple[int, int]:
    season, rnd = csv_path.stem.split("_R")
    return int(season), int(rnd)


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _luma(rgb: tuple[int, int, int]) -> float:
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255


def _mix(rgb: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(c + (t - c) * amount for c, t in zip(rgb, target))


def team_colors(team: str) -> tuple[str, str]:
    """Team colour adjusted so it stays visible on paper and on a dark screen."""
    base = _rgb(TEAM_COLORS.get(team, FALLBACK_COLOR))
    light, dark = base, base
    for _ in range(6):
        if _luma(light) <= 0.62:
            break
        light = _mix(light, (0, 0, 0), 0.22)
    for _ in range(6):
        if _luma(dark) >= 0.38:
            break
        dark = _mix(dark, (255, 255, 255), 0.3)
    return _hex(light), _hex(dark)


def _team_style(team) -> str:
    light, dark = team_colors("" if pd.isna(team) else str(team))
    return f"--team-l:{light};--team-d:{dark}"


def _cell(value) -> str:
    return "" if pd.isna(value) else html.escape(str(value))


def _pct(value) -> str:
    return "—" if pd.isna(value) else f"{float(value):.1f}"


def _grid_label(value) -> str:
    if pd.isna(value):
        return "—"
    return "PIT" if float(value) == 0 else f"{int(value)}"


def _move(grid, predicted) -> str:
    if pd.isna(grid) or float(grid) == 0:
        return ""
    places = int(grid) - int(predicted)
    if places == 0:
        return ""
    return f'<span class="move{" up" if places > 0 else ""}">{places:+d}</span>'


def _chart(rows: pd.DataFrame) -> str:
    if rows.empty:
        return ""
    ceiling = max(rows["PodiumPct"].max(), rows["WinPct"].max())
    scale = max(20, int(math.ceil(ceiling / 20.0) * 20))
    width, row_h, pad_l, pad_r, head = 640, 26, 78, 52, 26
    plot = width - pad_l - pad_r
    height = head + row_h * len(rows)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Win and podium chance for the leading {len(rows)} drivers">']
    for step in range(0, 5):
        frac = step / 4
        x = pad_l + plot * frac
        parts.append(f'<line x1="{x:.1f}" y1="{head - 7}" x2="{x:.1f}" y2="{height - 4}" '
                     f'stroke="var(--rule)" stroke-width="1" />')
        parts.append(f'<text x="{x:.1f}" y="{head - 13}" fill="var(--ink-3)" font-size="11" '
                     f'font-family="IBM Plex Mono, monospace" text-anchor="middle">{int(scale * frac)}</text>')
    for i, row in enumerate(rows.itertuples(index=False)):
        y = head + i * row_h
        style = _team_style(row.TeamName)
        podium = plot * min(float(row.PodiumPct), scale) / scale
        win = plot * min(float(row.WinPct), scale) / scale
        parts.append(f'<text x="14" y="{y + 15}" fill="var(--ink-3)" font-size="12" '
                     f'font-family="IBM Plex Mono, monospace" text-anchor="end">{i + 1}</text>')
        parts.append(f'<text x="24" y="{y + 16}" fill="var(--ink)" font-size="17" font-weight="600" '
                     f'font-family="Barlow Condensed, sans-serif">{html.escape(str(row.Abbreviation))}</text>')
        parts.append(f'<rect class="bar-soft" style="{style}" x="{pad_l}" y="{y + 3}" '
                     f'width="{podium:.1f}" height="15" />')
        parts.append(f'<rect class="bar" style="{style}" x="{pad_l}" y="{y + 3}" '
                     f'width="{win:.1f}" height="15" />')
        parts.append(f'<text x="{pad_l + podium + 7:.1f}" y="{y + 15}" fill="var(--ink-3)" font-size="12" '
                     f'font-family="IBM Plex Mono, monospace">{float(row.PodiumPct):.0f}</text>')
        if podium - win > 28:
            parts.append(f'<text x="{pad_l + win + 7:.1f}" y="{y + 15}" fill="var(--ink-2)" font-size="12" '
                         f'font-weight="600" font-family="IBM Plex Mono, monospace">'
                         f'{float(row.WinPct):.0f}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _table(pred: pd.DataFrame) -> str:
    head = ("<thead><tr><th></th><th></th><th class='left'>Driver</th><th class='left team'>Team</th>"
            "<th>Grid</th><th>Win</th><th>Podium</th><th>Points</th><th>DNF</th></tr></thead>")
    rows = []
    for row in pred.itertuples(index=False):
        dnf = 0.0 if pd.isna(row.DnfPct) else float(row.DnfPct)
        risk = " class='num risk'" if dnf >= 20 else " class='num'"
        rows.append(
            f"<tr><td class='pos num'>{int(row.PredictedPosition)}</td>"
            f"<td class='mark-cell'><span class='mark' style='{_team_style(row.TeamName)}'></span></td>"
            f"<td class='drv'>{_cell(row.Abbreviation)}</td>"
            f"<td class='team'>{_cell(row.TeamName)}</td>"
            f"<td class='num'>{_grid_label(row.Grid)}{_move(row.Grid, row.PredictedPosition)}</td>"
            f"<td class='num win'>{_pct(row.WinPct)}</td><td class='num'>{_pct(row.PodiumPct)}</td>"
            f"<td class='num'>{_pct(row.PointsPct)}</td><td{risk}>{_pct(row.DnfPct)}</td></tr>"
        )
    return f"<div class='scroller'><table>{head}<tbody>{''.join(rows)}</tbody></table></div>"


def _footer(pred: pd.DataFrame, stamp: pd.Timestamp) -> str:
    lines = []
    overrides = pred["GridOverrides"].iloc[0] if "GridOverrides" in pred else None
    if isinstance(overrides, str) and overrides.strip():
        lines.append(f"<p>{html.escape(overrides)}</p>")
    warnings = pred["Warnings"].iloc[0] if "Warnings" in pred else None
    if isinstance(warnings, str) and warnings.strip():
        for warning in warnings.split("; "):
            lines.append(f"<p class='warn'>Data check: {html.escape(warning)}</p>")
    if "Temperature" in pred and not pd.isna(pred["Temperature"].iloc[0]):
        races = pred["CalibrationRaces"].iloc[0] if "CalibrationRaces" in pred else None
        tail = f", calibrated on {int(races)} earlier races" if not pd.isna(races) else ""
        lines.append(f"<p>Probability spread {float(pred['Temperature'].iloc[0]):.2f}{tail}.</p>")
    if not pd.isna(stamp):
        lines.append(f"<p class='num'>{stamp:%Y-%m-%d %H:%M} UTC</p>")
    return f"<hr class='rule'><footer>{''.join(lines)}</footer>"


def render(csv_path: Path) -> str:
    pred = pd.read_csv(csv_path).sort_values("PredictedPosition")
    season, rnd = _season_round(Path(csv_path))
    event = str(pred["EventName"].iloc[0]) if "EventName" in pred else f"Round {rnd}"
    pre_race = bool(pred["PreRace"].all()) if "PreRace" in pred else False
    stamp = pd.to_datetime(pred["PredictedAtUTC"].iloc[0], errors="coerce") if "PredictedAtUTC" in pred else pd.NaT

    favourite = pred.sort_values("WinPct", ascending=False).iloc[0]
    podium = pred.sort_values("PodiumPct", ascending=False)["Abbreviation"].head(3)
    tag = ('<span class="tag"><i></i>Predicted before the race</span>' if pre_race
           else '<span class="tag after"><i></i>Made after the race — not a forecast</span>')
    when = ""
    if not pd.isna(stamp):
        when = (f"<p class='stamp'>Made {stamp:%a %d %b %Y, %H:%M} UTC "
                f"· {stamp + MANILA_OFFSET:%H:%M} Manila</p>")

    return f"""<title>{html.escape(event)} Prediction</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{STYLE}</style>
<div class="wrap">
  <header>
    <p class="meta"><span class="rnd num">Round {rnd}</span><span>{season} season</span></p>
    <h1>{html.escape(event)}</h1>
    {when}
    {tag}
  </header>

  <hr class="rule heavy">
  <div class="headline">
    <span class="code">{_cell(favourite['Abbreviation'])}</span>
    <span class="pct num">{_pct(favourite['WinPct'])}% to win</span>
    <span class="sub">Most likely podium: <b>{html.escape(", ".join(podium))}</b></span>
  </div>

  <hr class="rule">
  <h2>Chance of winning</h2>
  <p class="legend"><span><i></i>Win</span><span><i class="soft"></i>Podium</span></p>
  {_chart(pred.head(CHART_ROWS))}

  <hr class="rule">
  <h2>Full field</h2>
  {_table(pred)}

  <hr class="rule">
  <h2>How to read this</h2>
  <div class="note">
    <p>The predicted order sits close to the starting grid, and that is expected. This model has
    <strong>not</strong> been shown to predict the finishing order any better than assuming everyone
    finishes where they start.</p>
    <p>The percentages are what it adds. They are checked against past races and come out about right
    on average, which a starting grid on its own cannot tell you.</p>
    <p>Grid penalties are only included if they were entered by hand — they are never published in the
    timing data this is built from.</p>
  </div>
  {_footer(pred, stamp)}
</div>
"""


def run(season: int, rnd: int) -> Path:
    csv_path = PREDICTIONS_DIR / f"{season}_R{rnd:02d}.csv"
    if not csv_path.exists():
        raise SystemExit(f"No saved prediction at {csv_path}; run `predict` first.")
    out_path = csv_path.with_suffix(".html")
    out_path.write_text(render(csv_path), encoding="utf-8")
    print(f"Wrote {out_path}")
    return out_path

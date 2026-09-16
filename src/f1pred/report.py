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

STYLE = """
:root {
  --surface: #fcfcfb;
  --raised: #ffffff;
  --ink: #0b0b0b;
  --ink-2: #52514e;
  --muted: #898781;
  --rule: #e1e0d9;
  --accent: #2a78d6;
  --accent-soft: #cde2fb;
  --warn: #a8501c;
  --warn-soft: #f6e4d6;
  --shadow: 0 1px 2px rgba(11, 11, 11, .06);
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --surface: #121211;
    --raised: #1b1b18;
    --ink: #f4f3ef;
    --ink-2: #b8b6ae;
    --muted: #8d8b83;
    --rule: #33322d;
    --accent: #6da7ec;
    --accent-soft: #1f3a5c;
    --warn: #e0a077;
    --warn-soft: #3a2517;
    --shadow: none;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --surface: #121211;
  --raised: #1b1b18;
  --ink: #f4f3ef;
  --ink-2: #b8b6ae;
  --muted: #8d8b83;
  --rule: #33322d;
  --accent: #6da7ec;
  --accent-soft: #1f3a5c;
  --warn: #e0a077;
  --warn-soft: #3a2517;
  --shadow: none;
  color-scheme: dark;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding-block: 32px 56px;
  padding-left: 16px;
  padding-right: 16px;
  background: var(--surface);
  color: var(--ink);
  font-family: "Source Sans 3", ui-sans-serif, system-ui, "Segoe UI", sans-serif;
  font-size: 16px;
  line-height: 1.55;
}
.wrap { max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 28px; }
.eyebrow {
  font-family: "Archivo", ui-sans-serif, system-ui, sans-serif;
  font-size: 12px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); margin: 0;
}
h1 {
  font-family: "Archivo", ui-sans-serif, system-ui, sans-serif;
  font-size: clamp(28px, 6vw, 44px); font-weight: 700; letter-spacing: -.02em; line-height: 1.08;
  margin: 6px 0 0; text-wrap: balance;
}
.badge {
  display: inline-flex; align-items: center; gap: 7px; align-self: flex-start;
  padding: 5px 12px; border-radius: 999px; font-size: 13px; font-weight: 600;
  background: var(--accent-soft); color: var(--accent);
}
.badge.after { background: var(--warn-soft); color: var(--warn); }
.dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.stamp { color: var(--ink-2); font-size: 14px; margin: 10px 0 0; }
.headline {
  background: var(--raised); border: 1px solid var(--rule); border-radius: 10px;
  padding: 20px 22px; box-shadow: var(--shadow);
}
.headline .fav {
  font-family: "Archivo", ui-sans-serif, system-ui, sans-serif;
  font-size: 26px; font-weight: 700; letter-spacing: -.01em; margin: 0;
}
.headline .fav span { color: var(--accent); }
.headline p { margin: 6px 0 0; color: var(--ink-2); }
h2 {
  font-family: "Archivo", ui-sans-serif, system-ui, sans-serif;
  font-size: 13px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 12px;
}
.legend { display: flex; gap: 18px; font-size: 13px; color: var(--ink-2); margin: 0 0 10px; }
.key { display: inline-flex; align-items: center; gap: 6px; }
.swatch { width: 12px; height: 12px; border-radius: 3px; }
svg { width: 100%; height: auto; display: block; }
.scroller { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }
th {
  font-family: "Archivo", ui-sans-serif, system-ui, sans-serif;
  font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted); text-align: right; padding: 0 10px 8px; white-space: nowrap;
}
th.left, td.left { text-align: left; }
td { padding: 7px 10px; border-top: 1px solid var(--rule); text-align: right; white-space: nowrap; }
td.pos { color: var(--muted); width: 34px; }
td.drv { font-weight: 600; }
td.team { color: var(--ink-2); }
.chip { font-size: 12px; padding: 1px 6px; border-radius: 4px; color: var(--muted); }
.chip.up { background: var(--accent-soft); color: var(--accent); }
.chip.down { background: var(--warn-soft); color: var(--warn); }
.risk { color: var(--warn); font-weight: 600; }
.note {
  background: var(--raised); border: 1px solid var(--rule); border-left: 3px solid var(--accent);
  border-radius: 8px; padding: 16px 18px;
}
.note h2 { margin-bottom: 8px; }
.note p { margin: 0 0 10px; color: var(--ink-2); font-size: 15px; }
.note p:last-child { margin-bottom: 0; }
footer { border-top: 1px solid var(--rule); padding-top: 16px; color: var(--muted); font-size: 13px; }
footer p { margin: 0 0 6px; }
footer .warn { color: var(--warn); }
"""


def _season_round(csv_path: Path) -> tuple[int, int]:
    season, rnd = csv_path.stem.split("_R")
    return int(season), int(rnd)


def _cell(value) -> str:
    return "" if pd.isna(value) else html.escape(str(value))


def _pct(value) -> str:
    return "—" if pd.isna(value) else f"{float(value):.1f}"


def _grid_label(value) -> str:
    if pd.isna(value):
        return "—"
    return "PIT" if float(value) == 0 else f"{int(value)}"


def _delta_chip(grid, predicted) -> str:
    if pd.isna(grid) or float(grid) == 0:
        return ""
    move = int(grid) - int(predicted)
    if move == 0:
        return '<span class="chip">=</span>'
    style = "up" if move > 0 else "down"
    return f'<span class="chip {style}">{move:+d}</span>'


def _chart(rows: pd.DataFrame) -> str:
    if rows.empty:
        return ""
    top = max(rows["PodiumPct"].max(), rows["WinPct"].max())
    scale = max(20, int(math.ceil(top / 20.0) * 20))
    width, row_h, pad_l, pad_r, head = 600, 27, 52, 48, 28
    plot = width - pad_l - pad_r
    height = head + row_h * len(rows) + 6
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Win and podium chance for the top {len(rows)} drivers">']
    for frac in (0, 0.25, 0.5, 0.75, 1):
        x = pad_l + plot * frac
        parts.append(f'<line x1="{x:.1f}" y1="{head - 8}" x2="{x:.1f}" y2="{height - 6}" '
                     f'stroke="var(--rule)" stroke-width="1" />')
        parts.append(f'<text x="{x:.1f}" y="{head - 14}" fill="var(--muted)" font-size="10" '
                     f'text-anchor="middle">{int(scale * frac)}%</text>')
    for i, row in enumerate(rows.itertuples(index=False)):
        y = head + i * row_h
        podium = plot * min(float(row.PodiumPct), scale) / scale
        win = plot * min(float(row.WinPct), scale) / scale
        parts.append(f'<text x="{pad_l - 9}" y="{y + 15}" fill="var(--ink)" font-size="12" '
                     f'font-weight="600" text-anchor="end">{html.escape(str(row.Abbreviation))}</text>')
        parts.append(f'<rect x="{pad_l}" y="{y + 3}" width="{podium:.1f}" height="16" rx="3" '
                     f'fill="var(--accent-soft)" />')
        parts.append(f'<rect x="{pad_l}" y="{y + 3}" width="{win:.1f}" height="16" rx="3" '
                     f'fill="var(--accent)" />')
        parts.append(f'<text x="{pad_l + max(podium, win) + 7:.1f}" y="{y + 15}" fill="var(--ink-2)" '
                     f'font-size="11">{float(row.WinPct):.0f}%</text>')
    parts.append("</svg>")
    return "".join(parts)


def _table(pred: pd.DataFrame) -> str:
    head = ("<thead><tr><th></th><th class='left'>Driver</th><th class='left'>Team</th><th>Grid</th>"
            "<th>Win</th><th>Podium</th><th>Points</th><th>DNF</th></tr></thead>")
    rows = []
    for row in pred.itertuples(index=False):
        dnf = float(row.DnfPct) if not pd.isna(row.DnfPct) else 0.0
        risk = " class='risk'" if dnf >= 20 else ""
        rows.append(
            f"<tr><td class='pos'>{int(row.PredictedPosition)}</td>"
            f"<td class='left drv'>{_cell(row.Abbreviation)}</td>"
            f"<td class='left team'>{_cell(row.TeamName)}</td>"
            f"<td>{_grid_label(row.Grid)} {_delta_chip(row.Grid, row.PredictedPosition)}</td>"
            f"<td>{_pct(row.WinPct)}</td><td>{_pct(row.PodiumPct)}</td>"
            f"<td>{_pct(row.PointsPct)}</td><td{risk}>{_pct(row.DnfPct)}</td></tr>"
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
        lines.append(f"<p>Generated {stamp:%d %b %Y, %H:%M} UTC.</p>")
    return f"<footer>{''.join(lines)}</footer>"


def render(csv_path: Path) -> str:
    pred = pd.read_csv(csv_path).sort_values("PredictedPosition")
    season, rnd = _season_round(Path(csv_path))
    event = str(pred["EventName"].iloc[0]) if "EventName" in pred else f"Round {rnd}"
    pre_race = bool(pred["PreRace"].all()) if "PreRace" in pred else False
    stamp = pd.to_datetime(pred["PredictedAtUTC"].iloc[0], errors="coerce") if "PredictedAtUTC" in pred else pd.NaT

    favourite = pred.sort_values("WinPct", ascending=False).iloc[0]
    podium = ", ".join(pred.sort_values("PodiumPct", ascending=False)["Abbreviation"].head(3))
    badge = ('<span class="badge"><span class="dot"></span>Predicted before the race</span>' if pre_race
             else '<span class="badge after"><span class="dot"></span>Made after the race — not a forecast</span>')
    when = ""
    if not pd.isna(stamp):
        when = (f"<p class='stamp'>Made {stamp:%a %d %b, %H:%M} UTC "
                f"({stamp + MANILA_OFFSET:%H:%M} Manila)</p>")

    return f"""<title>{html.escape(event)} Prediction</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=Source+Sans+3:wght@400;600&display=swap">
<style>{STYLE}</style>
<div class="wrap">
  <header>
    <p class="eyebrow">Formula 1 · {season} · Round {rnd}</p>
    <h1>{html.escape(event)}</h1>
    {when}
  </header>
  {badge}
  <section class="headline">
    <p class="fav">{_cell(favourite['Abbreviation'])} <span>{_pct(favourite['WinPct'])}% to win</span></p>
    <p>Most likely podium: {html.escape(podium)}</p>
  </section>
  <section>
    <h2>Chance of winning</h2>
    <div class="legend">
      <span class="key"><span class="swatch" style="background: var(--accent)"></span>Win</span>
      <span class="key"><span class="swatch" style="background: var(--accent-soft)"></span>Podium</span>
    </div>
    {_chart(pred.head(CHART_ROWS))}
  </section>
  <section>
    <h2>Every driver</h2>
    {_table(pred)}
  </section>
  <section class="note">
    <h2>How to read this</h2>
    <p>The predicted order sits close to the starting grid, and that is expected. This model has
    <strong>not</strong> been shown to predict the finishing order any better than simply assuming
    everyone finishes where they start.</p>
    <p>The percentages are what it adds. They are checked against past races and come out about right
    on average, which is something a starting grid on its own cannot tell you.</p>
    <p>Grid penalties are not included unless they were entered by hand — they are never published in
    the timing data this is built from.</p>
  </section>
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

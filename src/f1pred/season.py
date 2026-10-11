"""Season scorecard page: every saved prediction scored against its result."""
from __future__ import annotations

import html

import pandas as pd

from f1pred import build, config, score
from f1pred.report import STYLE, screenshot, standalone

PODIUM_BINS = [0, 5, 20, 50, 80, 100]
SUMMARY_ROWS = [
    ("Spearman", "Order match", "{:.2f}"),
    ("WinnerHit", "Winner right", "{:.0%}"),
    ("PodiumHitRate", "Podium spots right", "{:.0%}"),
    ("MAE", "Places off, average", "{:.1f}"),
]

SEASON_STYLE = """
.dumb line.link { stroke: var(--rule-strong); stroke-width: 2; }
.dumb circle.model { fill: var(--signal); stroke: var(--bg); stroke-width: 2; }
.dumb circle.grid { fill: var(--bg); stroke: var(--ink-3); stroke-width: 2; }
.dumb g.race:hover text.name { fill: var(--ink); }
.key { display: flex; gap: 16px; font-size: 13px; color: var(--ink-3); margin: 0 0 10px; }
.key i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; vertical-align: middle;
  margin-right: 6px; }
.key i.model { background: var(--signal); }
.key i.grid { border: 2px solid var(--ink-3); }
.key i.said { border-radius: 0; width: 22px; height: 9px; background: var(--ink-3); opacity: .45; }
.key i.did { border-radius: 0; width: 22px; height: 9px; background: var(--ink-2); }
.cal rect.said { fill: var(--ink-3); fill-opacity: .45; }
.cal rect.did { fill: var(--ink-2); }
td.lbl { text-align: left; color: var(--ink-2); }
svg.dumb, svg.cal { max-width: 680px; }
th.grp { text-align: center; color: var(--ink-2); }
thead tr:first-child th:first-child { border-bottom: 0; }
td.better { font-weight: 600; color: var(--ink); }
"""


def season_data(season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-race scores and per-driver rows for every saved prediction with a full result."""
    entries = build.load_processed()[0]
    races, drivers = [], []
    for s, rnd, pred in score.load_predictions(season):
        actual = entries[(entries["Season"] == s) & (entries["RoundNumber"] == rnd)]
        merged = score.merge_actual(pred, actual)
        if merged is None:
            continue
        live = score.is_pre_race(pred)
        row = score.score_race(pred, actual)
        races.append({"RoundNumber": rnd, "EventName": actual["EventName"].iloc[0], "Live": live, **row})
        drivers.append(merged.assign(RoundNumber=rnd, Live=live,
                                     OnPodium=merged["FinishPosition"].rank(method="first") <= 3))
    if not races:
        raise SystemExit(f"No scored predictions for {season} yet.")
    return pd.DataFrame(races).sort_values("RoundNumber"), pd.concat(drivers, ignore_index=True)


def podium_calibration(drivers: pd.DataFrame) -> pd.DataFrame:
    """Predicted podium chance against how often it happened, in bands."""
    bands = pd.cut(drivers["PodiumPct"], PODIUM_BINS, include_lowest=True)
    out = drivers.groupby(bands, observed=True).agg(
        Said=("PodiumPct", "mean"), Did=("OnPodium", "mean"), N=("OnPodium", "size"))
    out["Did"] *= 100
    out.index = [f"{int(b.left)}–{int(b.right)}%" for b in out.index]
    return out


def _summary(races: pd.DataFrame) -> str:
    groups = [("All races", races), ("Live only", races[races["Live"]])]
    head = "<tr><th></th>" + "".join(
        f"<th class='grp' colspan='2'>{name} ({len(g)})</th>" for name, g in groups) + "</tr>"
    head += "<tr><th></th>" + "<th>Model</th><th>Grid</th>" * len(groups) + "</tr>"
    rows = []
    for metric, label, fmt in SUMMARY_ROWS:
        cells = []
        for _, g in groups:
            if g.empty:
                cells += ["<td class='num'>—</td>"] * 2
                continue
            model, grid = g[metric].mean(), g[f"Grid{metric}"].mean()
            model_wins = model < grid if metric == "MAE" else model > grid
            cls = "num better" if model_wins else "num"
            cells += [f"<td class='{cls}'>{fmt.format(model)}</td>", f"<td class='num'>{fmt.format(grid)}</td>"]
        rows.append(f"<tr><td class='lbl'>{label}</td>{''.join(cells)}</tr>")
    winner = "".join(
        (f"<td class='num'>{g['WinnerWinPct'].mean():.0f}%</td>" if not g.empty else "<td class='num'>—</td>")
        + "<td class='num'>—</td>" for _, g in groups)
    rows.append(f"<tr><td class='lbl'>Win chance given to the winner</td>{winner}</tr>")
    return f"<div class='scroller'><table><thead>{head}</thead><tbody>{''.join(rows)}</tbody></table></div>"


def _dumbbell(races: pd.DataFrame) -> str:
    width, row_h, pad_l, pad_r, head = 480, 28, 122, 40, 26
    plot = width - pad_l - pad_r
    lo = min(0.0, float(races[["Spearman", "GridSpearman"]].min().min()))
    height = head + row_h * len(races)

    def x(v: float) -> float:
        return pad_l + plot * (v - lo) / (1 - lo)

    parts = [f'<svg class="dumb" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Order match per race, model against grid order">']
    for step in range(5):
        v = lo + (1 - lo) * step / 4
        parts.append(f'<line x1="{x(v):.1f}" y1="{head - 7}" x2="{x(v):.1f}" y2="{height - 4}" '
                     f'stroke="var(--rule)" stroke-width="1" />')
        parts.append(f'<text x="{x(v):.1f}" y="{head - 13}" fill="var(--ink-3)" font-size="12" '
                     f'font-family="IBM Plex Mono, monospace" text-anchor="middle">{v:.2f}</text>')
    for i, r in enumerate(races.itertuples(index=False)):
        y = head + i * row_h + 11
        name = html.escape(str(r.EventName).replace(" Grand Prix", ""))
        tip = (f"R{r.RoundNumber} {name}: model {r.Spearman:.2f}, grid {r.GridSpearman:.2f}"
               f"{'' if r.Live else ' (made after the race)'}")
        parts.append(f'<g class="race"><title>{tip}</title>')
        parts.append(f'<rect x="0" y="{y - 12}" width="{width}" height="{row_h}" fill="transparent" />')
        parts.append(f'<text x="22" y="{y + 4}" fill="var(--ink-3)" font-size="12" text-anchor="end" '
                     f'font-family="IBM Plex Mono, monospace">{r.RoundNumber}</text>')
        parts.append(f'<text class="name" x="30" y="{y + 5}" fill="var(--ink-2)" font-size="15" '
                     f'font-weight="{600 if r.Live else 500}" font-family="Barlow Condensed, sans-serif">'
                     f'{name}</text>')
        parts.append(f'<line class="link" x1="{x(r.GridSpearman):.1f}" y1="{y}" x2="{x(r.Spearman):.1f}" y2="{y}" />')
        parts.append(f'<circle class="grid" cx="{x(r.GridSpearman):.1f}" cy="{y}" r="5" />')
        parts.append(f'<circle class="model" cx="{x(r.Spearman):.1f}" cy="{y}" r="5" />')
        if r.Live:
            parts.append(f'<text x="{width - 4}" y="{y + 4}" fill="var(--signal)" font-size="12" font-weight="600" '
                         f'text-anchor="end" font-family="IBM Plex Mono, monospace">LIVE</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def _calibration(cal: pd.DataFrame) -> str:
    width, row_h, pad_l, pad_r, head = 480, 40, 70, 52, 26
    plot = width - pad_l - pad_r
    height = head + row_h * len(cal)
    parts = [f'<svg class="cal" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Predicted podium chance against how often it happened">']
    for step in range(5):
        v = step * 25
        xv = pad_l + plot * v / 100
        parts.append(f'<line x1="{xv:.1f}" y1="{head - 7}" x2="{xv:.1f}" y2="{height - 4}" '
                     f'stroke="var(--rule)" stroke-width="1" />')
        parts.append(f'<text x="{xv:.1f}" y="{head - 13}" fill="var(--ink-3)" font-size="12" '
                     f'font-family="IBM Plex Mono, monospace" text-anchor="middle">{v}</text>')
    for i, (band, r) in enumerate(cal.iterrows()):
        y = head + i * row_h
        tip = f"Said {band}: averaged {r.Said:.0f}%, happened {r.Did:.0f}% of {int(r.N)} times"
        parts.append(f"<g><title>{tip}</title>")
        parts.append(f'<text x="{pad_l - 10}" y="{y + 21}" fill="var(--ink-2)" font-size="13" text-anchor="end" '
                     f'font-family="IBM Plex Mono, monospace">{band}</text>')
        parts.append(f'<rect class="said" x="{pad_l}" y="{y + 4}" width="{plot * r.Said / 100:.1f}" height="14" />')
        parts.append(f'<rect class="did" x="{pad_l}" y="{y + 20}" width="{plot * r.Did / 100:.1f}" height="14" />')
        parts.append(f'<text x="{pad_l + plot * max(r.Said, r.Did) / 100 + 8:.1f}" y="{y + 23}" fill="var(--ink-3)" '
                     f'font-size="12" font-family="IBM Plex Mono, monospace">n={int(r.N)}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def render(season: int, races: pd.DataFrame, drivers: pd.DataFrame) -> str:
    beat = int((races["Spearman"] > races["GridSpearman"]).sum())
    live = races[races["Live"]]
    live_line = (f"Live, before the race: <b>{int((live['Spearman'] > live['GridSpearman']).sum())} of "
                 f"{len(live)}</b> beat grid order." if len(live) else "No live predictions scored yet.")
    return f"""<title>{season} Season Scorecard</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{STYLE}{SEASON_STYLE}</style>
<div class="wrap">
  <header>
    <p class="meta"><span class="rnd num">{len(races)} races</span><span>{season} season</span></p>
    <h1>Season scorecard</h1>
  </header>

  <hr class="rule heavy">
  <div class="headline">
    <span class="code num">{beat}/{len(races)}</span>
    <span class="pct">races where the model's order beat the grid's</span>
    <span class="sub">{live_line}</span>
  </div>

  <hr class="rule">
  <h2>Totals</h2>
  {_summary(races)}

  <hr class="rule">
  <h2>Race by race</h2>
  <p class="key"><span><i class="model"></i>Model</span><span><i class="grid"></i>Grid order</span>
  <span>Order match, 1 is perfect</span></p>
  {_dumbbell(races)}

  <hr class="rule">
  <h2>Do the percentages hold up?</h2>
  <p class="key"><span><i class="said"></i>Podium chance it gave</span><span><i class="did"></i>How often it happened</span></p>
  {_calibration(podium_calibration(drivers))}

  <hr class="rule">
  <h2>How to read this</h2>
  <div class="note">
    <p>Races marked <strong>LIVE</strong> were predicted after qualifying, before the race. The rest
    were made afterwards, but each one only used races that came before it.</p>
    <p>If the percentages are honest, the two bars in each band come out about the same length. Bands
    with few drivers in them bounce around, so read the small ones loosely.</p>
  </div>
</div>
"""


def run(season: int, png: bool = True):
    races, drivers = season_data(season)
    out_path = config.PREDICTIONS_DIR / str(season) / f"{season}_season.html"
    out_path.write_text(standalone(render(season, races, drivers)), encoding="utf-8")
    print(f"Wrote {out_path}")
    png_path = screenshot(out_path) if png else None
    if png_path:
        print(f"Wrote {png_path}, ready to send as a picture.")
    return out_path

"""Static site of every saved prediction, for GitHub Pages."""
from __future__ import annotations

import html
import shutil
from pathlib import Path

import pandas as pd

from f1pred import build, config, report, score, season

SITE_STYLE = """
td.race { text-align: left; }
td.race a { color: var(--ink); text-decoration: none; font-weight: 600; }
td.race a:hover { border-bottom: 1px solid var(--ink); }
td.pick { text-align: left; }
.live { color: var(--signal); font-family: "IBM Plex Mono", monospace; font-size: 11px; font-weight: 600;
  margin-left: 6px; }
td.ok { color: var(--ink); font-weight: 600; }
td.miss { color: var(--ink-3); }
.lede { color: var(--ink-2); max-width: 62ch; margin: 14px 0 0; }
.lede a, .cta a, footer a { color: var(--ink-2); }
.cta { margin: 18px 0 0; font-size: 15px; }
"""


def page_name(rnd: int) -> str:
    return f"round-{rnd:02d}.html"


def _link(href: str, label: str) -> str:
    return f'<a href="{href}">{html.escape(label)}</a>'


def race_nav(rounds: list[int], rnd: int, has_scorecard: bool = True) -> str:
    i = rounds.index(rnd)
    parts = [_link("../index.html", "← All races")]
    if has_scorecard:
        parts.append(_link("scorecard.html", "Season scorecard"))
    parts.append('<span class="spacer"></span>')
    if i > 0:
        parts.append(_link(page_name(rounds[i - 1]), f"‹ Round {rounds[i - 1]}"))
    if i < len(rounds) - 1:
        parts.append(_link(page_name(rounds[i + 1]), f"Round {rounds[i + 1]} ›"))
    return f'<nav class="nav">{"".join(parts)}</nav>'


def event_name(pred: pd.DataFrame, actual: pd.DataFrame, rnd: int) -> str:
    if "EventName" in pred:
        return str(pred["EventName"].iloc[0])
    return str(actual["EventName"].iloc[0]) if not actual.empty else f"Round {rnd}"


def index_rows(season_no: int, predictions: list[tuple[int, int, pd.DataFrame]],
               entries: pd.DataFrame) -> list[dict]:
    rows = []
    for s, rnd, pred in predictions:
        if s != season_no:
            continue
        actual = entries[(entries["Season"] == s) & (entries["RoundNumber"] == rnd)]
        result = score.race_result(actual)
        fav = pred.sort_values("WinPct", ascending=False).iloc[0]
        winner = None if result is None or not (result == "1").any() else str(result[result == "1"].index[0])
        rows.append({
            "Round": rnd,
            "Event": event_name(pred, actual, rnd),
            "Pick": str(fav["Abbreviation"]), "PickPct": float(fav["WinPct"]),
            "Winner": winner, "Live": score.is_pre_race(pred),
        })
    return rows


def _index_table(season_no: int, rows: list[dict]) -> str:
    head = ("<thead><tr><th></th><th class='left'>Race</th><th class='left'>Favourite</th>"
            "<th class='left'>Winner</th><th></th></tr></thead>")
    body = []
    for r in rows:
        href = f"{season_no}/{page_name(r['Round'])}"
        name = r["Event"].replace(" Grand Prix", "")
        if r["Winner"] is None:
            winner, verdict = "<td class='pick miss'>pending</td>", "<td></td>"
        else:
            hit = r["Winner"] == r["Pick"]
            winner = f"<td class='pick'>{html.escape(r['Winner'])}</td>"
            verdict = "<td class='ok'>✓</td>" if hit else "<td class='miss'>✗</td>"
        live = " <span class='live'>LIVE</span>" if r["Live"] else ""
        body.append(
            f"<tr><td class='pos num'>{r['Round']}</td><td class='race'>{_link(href, name)}{live}</td>"
            f"<td class='pick'><b>{html.escape(r['Pick'])}</b> <span class='move num'>{r['PickPct']:.0f}%</span></td>"
            f"{winner}{verdict}</tr>")
    return f"<div class='scroller'><table>{head}<tbody>{''.join(body)}</tbody></table></div>"


def render_index(sections: list[tuple[int, list[dict], bool]]) -> str:
    blocks = []
    for season_no, rows, has_scorecard in sections:
        scored = [r for r in rows if r["Winner"] is not None]
        hits = sum(r["Winner"] == r["Pick"] for r in scored)
        cta = (f"<p class='cta'>{_link(f'{season_no}/scorecard.html', 'Season scorecard →')} "
               f"How the model did against plain grid order, and whether its percentages held up.</p>"
               if has_scorecard else "")
        blocks.append(f"""
  <hr class="rule heavy">
  <div class="headline">
    <span class="code num">{hits}/{len(scored)}</span>
    <span class="pct">winners picked in {season_no}</span>
    <span class="sub">The favourite is the driver given the highest chance to win.</span>
  </div>
  {cta}
  <hr class="rule">
  <h2>{season_no} races</h2>
  {_index_table(season_no, rows)}""")
    return f"""<title>F1 Race Predictions</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{report.STYLE}{SITE_STYLE}</style>
<div class="wrap">
  <header>
    <p class="meta"><span class="rnd">f1-prediction</span></p>
    <h1>F1 race predictions</h1>
    <p class="lede">Each race is predicted once qualifying is done: the likely finishing order, and every
    driver's chance to win, reach the podium, score points or retire. Races marked
    <span class="live">LIVE</span> were real forecasts, made before the race. The rest were made afterwards, using only the races
    before them.</p>
  </header>
  {''.join(blocks)}
  <hr class="rule">
  <footer><p>Built from FastF1 timing data. Code and method on
  <a href="https://github.com/rdgonzaga/f1-prediction">GitHub</a>.</p></footer>
</div>
"""


def build_site(out_dir: Path | None = None) -> Path:
    out_dir = Path(out_dir or config.SITE_DIR)
    predictions = score.load_predictions()
    if not predictions:
        raise SystemExit(f"No saved predictions in {config.PREDICTIONS_DIR}")
    entries = build.load_processed()[0]
    sections = []
    for season_no in sorted({s for s, _, _ in predictions}, reverse=True):
        season_dir = out_dir / str(season_no)
        shutil.rmtree(season_dir, ignore_errors=True)
        season_dir.mkdir(parents=True)
        try:
            races, drivers = season.season_data(season_no)
        except SystemExit:
            has_scorecard = False
        else:
            nav = f'<nav class="nav">{_link("../index.html", "← All races")}</nav>'
            (season_dir / "scorecard.html").write_text(
                report.standalone(season.render(season_no, races, drivers, nav=nav)), encoding="utf-8")
            has_scorecard = True
        rounds = sorted(r for s, r, _ in predictions if s == season_no)
        for rnd in rounds:
            actual = entries[(entries["Season"] == season_no) & (entries["RoundNumber"] == rnd)]
            page = report.render(config.prediction_path(season_no, rnd, ".csv"),
                                 result=score.race_result(actual), nav=race_nav(rounds, rnd, has_scorecard))
            (season_dir / page_name(rnd)).write_text(report.standalone(page), encoding="utf-8")
        sections.append((season_no, index_rows(season_no, predictions, entries), has_scorecard))
    (out_dir / "index.html").write_text(report.standalone(render_index(sections)), encoding="utf-8")
    print(f"Wrote the site to {out_dir} ({len(predictions)} race pages). Open index.html to check it.")
    return out_dir

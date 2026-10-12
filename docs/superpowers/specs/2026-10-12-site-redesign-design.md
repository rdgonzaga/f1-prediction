# Site redesign

Issue #32. Agreed with Rainer on 2026-10-12 through mockups in the brainstorming companion.

## Goal

Replace the v1 site (race list, race pages, scorecard) with a redesigned site in an F1 broadcast style. It serves three audiences at once: fans opening a shared link, people looking at the project, and Rainer checking it after a race. The latest race leads; the track record and method are one click away.

If the result looks bad, the fallback is a JSON export plus a JS frontend. That decision is made after reviewing screenshots, before merge.

## Look

- Dark only, F1 broadcast: near-black background, red accent rule (`#e10600`), team colours as stripes and bars.
- Titillium Web for text, JetBrains Mono for numbers (Google Fonts).
- Mobile first. Most visitors arrive from a shared link on a phone.
- Team colours use the existing dark-mode lightening logic from `report.team_colors`, so dark team colours stay visible.

## Pages

Top bar on every page: Home, Races, Drivers, Scorecard, How it works.

| Page | Path | Content |
|---|---|---|
| Home | `/` | Podium-first hero for the latest race. Season race cards below, newest first. Next race greyed out. Scorecard teaser. |
| Races | `/races/` | All race cards, grouped by season. |
| Race | `/<season>/round-NN/` | Podium-first hero, verdict line, tabs: Result vs prediction, Chances, Full field. |
| Drivers | `/drivers/` | Drivers grouped by team. |
| Driver | `/drivers/<driver_id>/` | Header in team colour, stats, season chart, race log. |
| Scorecard | `/<season>/scorecard/` | Totals vs grid order, race-by-race chart, podium calibration. |
| How it works | `/how-it-works/` | Plain-language explainer, adapted from the README. |

Every page is written as `<path>/index.html`. Old v1 URLs (`2026/round-17.html`) are dropped without redirects.

### Home hero (option C)

Three podium cards (P1 larger) with driver code, team, and win chance, coloured by team. Once the result is in, the hero also shows the verdict line. The full timing tower sits on the race page, linked from the hero.

### Race page (option C, with the option A table)

- **Verdict line:** whether the favourite won (and at what chance), how many of the three podium spots were called, and the biggest surprise. The surprise is the classified finisher with the largest gain over their predicted position, shown as "VER, 8th to 2nd".
- **Tab: Result vs prediction.** Timing-tower table: predicted position, team stripe, driver, win chance, finish. Exact hits get a check mark; others get an up or down arrow with the number of places. DNF, DSQ and DNS shown as labels.
- **Tab: Chances.** The win and podium bar chart for the top ten.
- **Tab: Full field.** Grid, win, podium, points and DNF chances for every driver.
- Before the result exists, the verdict reads "Result pending" and the first tab is hidden.
- Backfilled races are labelled "Made after the race"; live ones carry the red LIVE badge.
- Room for sprints later: a weekend can hold a second prediction as another section on the same page.

### Race archive (option A)

Card grid, newest first. Each card: round, LIVE badge if live, race name, pick and its win chance, winner, and a check or cross. The top stripe takes the winning team's colour (the pick's team while pending). The next race appears as a greyed card when the FastF1 schedule lookup works; otherwise it is left out.

### Driver page (option C)

- Header: name, current team, team colour.
- Stats: wins, podiums, races as favourite, how often the favourite pick was right, average places off between predicted and actual finish.
- Season chart: predicted and actual finish per round, two lines.
- Race log: round, race (linked), grid, predicted, win chance, finish.
- Retirements are excluded from places-off and from the chart line (shown as a gap).
- A driver who changed teams uses their latest team for the header; each race row uses that race's team.

## Code structure

New package `src/f1pred/web/` replacing `src/f1pred/site.py`.

- `data.py`: builds plain data for the templates from saved predictions and race results. Seasons, races (prediction rows, result labels, verdict, live flag), drivers (stats, race log), scorecard. Reuses `score.load_predictions`, `score.race_result`, `score.is_pre_race`, `season.season_data`, `season.podium_calibration`. No HTML.
- `charts.py`: inline SVG for the chance bars, the scorecard dumbbell and calibration charts (moved from `season.py`), and the driver season chart.
- `build.py`: Jinja2 environment over `web/templates/`, renders every page to `site/`, copies `web/static/`. Entry point `build_site(out_dir=None)`.
- `templates/`: `base.html` plus one template per page type and partials for the podium hero, timing tower and race card.
- `static/site.css`: the whole look. `static/site.js`: tabs only. Without JS every tab panel is shown in order.

`report` (local page plus PNG) and `season` render through the same templates with the CSS inlined so the file stands alone. The string-built HTML in `report.py` and `season.py` is removed; their data helpers stay.

Unchanged: the `site` command, the site rebuild at the end of `weekend` and `score`, the Pages workflow, and the commit-and-push routine.

New dependency: `jinja2==3.1.6` pinned in `requirements.txt`.

## Edge cases

- Pending result: verdict "Result pending", no result tab, archive card shows "pending".
- Season with no predictions: no pages; home falls back to the latest season that has predictions.
- Prediction CSV without `EventName`: fall back to the results' event name, then "Round N".
- Missing `DriverId` in an old CSV: match drivers by abbreviation within that season.

## Testing

- `data.py`: verdict (favourite hit and miss, podium count, surprise ignores retirements), driver stats, pending races, next-race fallback when the schedule lookup fails.
- Build: every expected page exists; every internal link resolves; a pending race has no result tab; a backfilled race carries the label.
- `report`: still writes a standalone `.html` and the `.png`.
- Visual: screenshots of home, a live race, a backfilled race, a driver page and the scorecard at 1280 and 390 px wide, shown to Rainer before merge.

## Rollout

One PR closing #32, with the rebuilt `site/` included, so the merge deploys it. Add `.superpowers/` to `.gitignore`. Update the README's website section.

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

import pandas as pd
import pytest

from f1pred.report import render

DRIVERS = ["ANT", "NOR", "VER", "HAM"]


def make_csv(tmp_path, pre_race=True, name="2026_R15.csv"):
    path = tmp_path / name
    pd.DataFrame({
        "PredictedPosition": [1, 2, 3, 4],
        "Abbreviation": DRIVERS,
        "TeamName": ["Mercedes", "McLaren", "Red Bull Racing", "Ferrari"],
        "Grid": [2.0, 1.0, 8.0, 0.0],
        "WinPct": [33.6, 40.8, 8.3, 6.7],
        "PodiumPct": [77.5, 74.6, 32.3, 28.1],
        "PointsPct": [92.9, 91.3, 89.1, 90.8],
        "DnfPct": [7.3, 8.8, 24.0, 9.0],
        "ExpectedPosition": [3.5, 3.9, 6.1, 6.1],
        "DriverId": ["antonelli", "norris", "verstappen", "hamilton"],
        "EventName": ["Azerbaijan Grand Prix"] * 4,
        "PreRace": pre_race,
        "PredictedAtUTC": ["2026-09-25 13:30:00"] * 4,
        "GridOverrides": ["Grid overrides: VER +5"] * 4,
        "Temperature": [0.4] * 4,
        "CalibrationRaces": [12] * 4,
        "Warnings": ["no weather or track status"] * 4,
    }).to_csv(path, index=False)
    return path


def test_pre_race_flag_decides_the_badge(tmp_path):
    before = render(make_csv(tmp_path, pre_race=True))
    assert "Predicted before the race" in before
    assert "not a forecast" not in before

    after = render(make_csv(tmp_path, pre_race=False, name="2026_R14.csv"))
    assert "not a forecast" in after
    assert "Predicted before the race" not in after


def test_every_driver_appears_in_predicted_order(tmp_path):
    table = render(make_csv(tmp_path)).split("<tbody>")[1].split("</tbody>")[0]
    positions = [table.index(code) for code in DRIVERS]
    assert positions == sorted(positions)
    assert table.count("<tr>") == len(DRIVERS)


def test_headline_names_the_highest_win_chance(tmp_path):
    page = render(make_csv(tmp_path))
    headline = page.split('class="headline"')[1].split("<hr")[0]
    assert "NOR" in headline
    assert "40.8% to win" in headline


def test_pit_lane_start_and_overrides_are_shown(tmp_path):
    page = render(make_csv(tmp_path))
    assert "PIT" in page
    assert "VER +5" in page


def test_saved_file_is_a_complete_page(tmp_path):
    from f1pred.report import standalone
    page = standalone(render(make_csv(tmp_path)))
    assert page.startswith("<!doctype html>")
    assert 'name="viewport"' in page
    assert page.count('<div class="wrap">') == 1
    assert page.index("<style>") < page.index("</head>") < page.index("<body>")
    assert page.rstrip().endswith("</html>")


def test_missing_prediction_is_reported(tmp_path, monkeypatch):
    from f1pred import report
    monkeypatch.setattr(report, "PREDICTIONS_DIR", tmp_path)
    with pytest.raises(SystemExit):
        report.run(2026, 99)

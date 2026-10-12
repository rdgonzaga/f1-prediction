import sys

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

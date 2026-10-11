import re

import pandas as pd
import pytest

from f1pred import score, site
from test_score import actual_frame, pred_frame


@pytest.fixture
def built(tmp_path, monkeypatch):
    monkeypatch.setattr(score.config, "PREDICTIONS_DIR", tmp_path / "predictions")
    for rnd, pre_race in [(1, False), (2, True), (3, True)]:
        path = score.config.prediction_path(2026, rnd, ".csv")
        path.parent.mkdir(parents=True)
        pred_frame(pre_race=pre_race).assign(
            EventName=f"Race {rnd} Grand Prix", TeamName="Ferrari", PointsPct=50.0, DnfPct=10.0).to_csv(
            path, index=False)
    entries = pd.concat([actual_frame(rnd=1), actual_frame(rnd=2), actual_frame(rnd=3).assign(Classified="")],
                        ignore_index=True)
    monkeypatch.setattr(site.build, "load_processed", lambda: (entries, None, None))
    return site.build_site(tmp_path / "site")


def test_site_has_index_scorecard_and_a_page_per_race(built):
    pages = sorted(p.relative_to(built).as_posix() for p in built.rglob("*.html"))
    assert pages == ["2026/round-01.html", "2026/round-02.html", "2026/round-03.html",
                     "2026/scorecard.html", "index.html"]


def test_every_relative_link_resolves(built):
    for page in built.rglob("*.html"):
        for href in re.findall(r'href="([^"]+)"', page.read_text(encoding="utf-8")):
            if href.startswith("http"):
                continue
            assert (page.parent / href).resolve().exists(), f"{page.name} -> {href}"


def test_scored_race_shows_result_and_dnf(built):
    page = (built / "2026" / "round-01.html").read_text(encoding="utf-8")
    assert "<th>Result</th>" in page
    assert ">DNF</td>" in page
    assert "Won by <b>A</b>" in page


def test_partial_result_is_pending(built):
    assert "<th>Result</th>" not in (built / "2026" / "round-03.html").read_text(encoding="utf-8")
    assert "pending" in (built / "index.html").read_text(encoding="utf-8")


def test_race_result_labels():
    result = score.race_result(actual_frame().assign(Classified=["1", "W", "D", "R"]))
    assert list(result) == ["1", "DNS", "DSQ", "DNF"]
    assert score.race_result(actual_frame().assign(Classified="")) is None

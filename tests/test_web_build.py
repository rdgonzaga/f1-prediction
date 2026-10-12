import re

import pandas as pd
import pytest

from f1pred import score
from f1pred.web import build as web
from test_score import actual_frame, pred_frame

IDS = ["alpha", "bravo", "charlie", "delta"]


@pytest.fixture
def built(tmp_path, monkeypatch):
    monkeypatch.setattr(score.config, "PREDICTIONS_DIR", tmp_path / "predictions")
    for rnd, pre_race in [(1, False), (2, True), (3, True)]:
        path = score.config.prediction_path(2026, rnd, ".csv")
        path.parent.mkdir(parents=True)
        pred_frame(pre_race=pre_race).assign(
            EventName=f"Race {rnd} & Co Grand Prix", TeamName="Ferrari", PointsPct=50.0, DnfPct=10.0,
            DriverId=IDS).to_csv(path, index=False)
    entries = pd.concat([actual_frame(rnd=1), actual_frame(rnd=2), actual_frame(rnd=3).assign(Classified="")],
                        ignore_index=True).assign(DriverId=IDS * 3)
    monkeypatch.setattr(score.build, "load_processed", lambda: (entries, None, None))
    out = tmp_path / "site"
    (out / "2026").mkdir(parents=True)
    (out / "2026" / "round-01.html").write_text("old", encoding="utf-8")
    return web.build_site(out, schedule=lambda year: pd.DataFrame(
        {"RoundNumber": [4], "EventName": ["Next Grand Prix"]}))


def read(root, rel):
    return (root / rel / "index.html").read_text(encoding="utf-8")


def test_every_page_is_written_and_old_pages_are_gone(built):
    pages = sorted(p.relative_to(built).as_posix() for p in built.rglob("*.html"))
    assert pages == [
        "2026/round-01/index.html", "2026/round-02/index.html", "2026/round-03/index.html",
        "2026/scorecard/index.html", "drivers/alpha/index.html", "drivers/bravo/index.html",
        "drivers/charlie/index.html", "drivers/delta/index.html", "drivers/index.html",
        "how-it-works/index.html", "index.html", "races/index.html"]
    assert (built / "static" / "site.css").exists() and (built / "static" / "site.js").exists()


def test_every_internal_link_resolves(built):
    for page in built.rglob("*.html"):
        for ref in re.findall(r'(?:href|src)="([^"]*)"', page.read_text(encoding="utf-8")):
            if ref.startswith(("http", "#")):
                continue
            target = page.parent / ref
            if ref.endswith("/") or ref in ("", "."):
                target = target / "index.html"
            assert target.resolve().exists(), f"{page.relative_to(built)} -> {ref}"


def test_pending_race_has_no_result_tab(built):
    pending = read(built, "2026/round-03")
    assert 'id="tab-result"' not in pending and "Result pending" in pending
    scored = read(built, "2026/round-02")
    assert 'id="tab-result"' in scored and ">DNF<" in scored
    assert "A won as favourite at 50%" in scored


def test_backfilled_race_is_labelled(built):
    assert "Made after the race" in read(built, "2026/round-01")
    live = read(built, "2026/round-02")
    assert "Made after the race" not in live and ">LIVE<" in live


def test_home_leads_with_the_latest_race_and_escapes_names(built):
    home = read(built, "")
    assert "Race 3 &amp; Co Grand Prix" in home and "Race 3 & Co" not in home
    assert "Next" in home and "2026/scorecard/" in home
    assert home.index("Race 3 &amp; Co") < home.index("Race 1 &amp; Co")


def test_driver_page_has_stats_and_log(built):
    page = read(built, "drivers/alpha")
    assert "Alpha" in page and "Races as favourite" in page
    assert page.count('href="../../2026/round-') >= 3

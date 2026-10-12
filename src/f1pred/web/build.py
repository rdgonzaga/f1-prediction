"""Render the static site, and standalone pages, from saved predictions."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from f1pred import build as processed
from f1pred import config, score
from f1pred.web import charts, data

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
SITE_URL = "https://rdgonzaga.github.io/f1-prediction/"


def _pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def environment() -> Environment:
    env = Environment(loader=FileSystemLoader(WEB_DIR / "templates"), autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["pct"] = _pct
    env.globals.update(charts=charts, ordinal=data.ordinal, scorecard_path=None)
    return env


def render_page(env: Environment, template: str, root: str, **context) -> str:
    return env.get_template(template).render(root=root, **context)


def _write(out_dir: Path, rel: str, page: str) -> None:
    path = out_dir / rel / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8", newline="\n")


def build_site(out_dir: Path | None = None,
               schedule: Callable[[int], pd.DataFrame] = data.fetch_schedule) -> Path:
    out_dir = Path(out_dir or config.SITE_DIR)
    predictions = score.load_predictions()
    if not predictions:
        raise SystemExit(f"No saved predictions in {config.PREDICTIONS_DIR}")
    site = data.load(predictions, processed.load_processed()[0], schedule)
    env = environment()
    if site.scorecard_season:
        env.globals["scorecard_path"] = site.scorecard_season.scorecard_path

    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.copytree(STATIC_DIR, out_dir / "static")

    def page(rel: str, template: str, root: str, **context) -> None:
        _write(out_dir, rel, render_page(env, template, root, site=site, **context))

    page("", "home.html", "./", active="home")
    page("races", "races.html", "../", active="races")
    page("drivers", "drivers.html", "../", active="drivers")
    page("how-it-works", "how.html", "../", active="how")
    for season in site.seasons:
        races = season.races
        for i, race in enumerate(races):
            page(race.path, "race.html", "../../", active="races", race=race,
                 prev_race=races[i - 1] if i else None, next_race=races[i + 1] if i + 1 < len(races) else None)
        if season.scorecard:
            page(season.scorecard_path, "scorecard.html", "../../", active="scorecard", season=season)
    for driver in site.drivers:
        page(driver.path, "driver.html", "../../", active="drivers", driver=driver)
    count = sum(len(s.races) for s in site.seasons)
    print(f"Wrote the site to {out_dir} ({count} race pages, {len(site.drivers)} drivers). "
          f"Open index.html to check it.")
    return out_dir

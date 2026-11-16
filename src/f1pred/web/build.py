"""Render the static site, and standalone pages, from saved predictions."""
from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from f1pred import build as processed
from f1pred import config, market, score
from f1pred.web import charts, data, share

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
SITE_URL = "https://f1.raigon.dev/"


def _pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def environment() -> Environment:
    env = Environment(loader=FileSystemLoader(WEB_DIR / "templates"), autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["pct"] = _pct
    env.globals.update(charts=charts, ordinal=data.ordinal, scorecard_path=None, site_url=SITE_URL)
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

    staging = out_dir.with_name(out_dir.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(STATIC_DIR, staging / "static")
    for size, name in ((32, "favicon-32.png"), (180, "apple-touch-icon.png")):
        share.save_icon(size, staging / "static" / name, out_dir / "static" / name)

    def page(rel: str, template: str, root: str, **context) -> None:
        _write(staging, rel, render_page(env, template, root, site=site, **context))

    def image(race: data.Race) -> None:
        share.save(race, staging / race.path / "share.png", out_dir / race.path / "share.png")

    try:
        _render_all(site, page, image)
        card = site.scorecard_season
        feed = latest_json(site.current.latest, card.scorecard if card else None)
        (staging / "latest.json").write_text(json.dumps(feed), encoding="utf-8")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if out_dir.exists():
        shutil.rmtree(out_dir)
    staging.rename(out_dir)
    count = sum(len(s.races) for s in site.seasons)
    print(f"Wrote the site to {out_dir} ({count} race pages, {len(site.drivers)} drivers). "
          f"Open index.html to check it.")
    return out_dir


def latest_json(race: data.Race, card: data.Scorecard | None = None) -> dict:
    """The newest race in a small feed, for other sites (raigon.dev) to show."""
    fav = race.favourite
    return {
        "season": race.season, "round": race.rnd, "race": race.short_name, "url": SITE_URL + race.path,
        "pending": race.pending, "favourite": {"code": fav.code, "win": round(fav.win, 1)},
        "podium": [r.code for r in race.podium], "winner": race.winner,
        "podium_called": None if race.verdict is None else race.verdict.podium_called,
        "live": None if card is None else live_record(card),
    }


def live_record(card: data.Scorecard) -> dict | None:
    """Model against the starting grid over the races predicted live."""
    live = card.races[card.races["Live"]].sort_values("RoundNumber")
    if live.empty:
        return None
    def mean(col: str, scale: int):
        value = float(live[col].mean()) * scale
        return round(value, 2) if scale == 1 else round(value)
    return {
        "races": len(live), "since": str(live.iloc[0]["EventName"]).removesuffix(" Grand Prix"),
        "podium": {"model": mean("PodiumHitRate", 100), "grid": mean("GridPodiumHitRate", 100)},
        "spearman": {"model": mean("Spearman", 1), "grid": mean("GridSpearman", 1)},
        "winner": {"model": mean("WinnerHit", 100), "grid": mean("GridWinnerHit", 100)},
    }


def _render_all(site: data.Site, page: Callable[..., None], image: Callable[[data.Race], None]) -> None:
    page("", "home.html", "./", active="home", share_race=site.current.latest)
    page("races", "races.html", "../", active="races")
    page("drivers", "drivers.html", "../", active="drivers")
    page("how-it-works", "how.html", "../", active="how")
    for season in site.seasons:
        races = season.races
        for i, race in enumerate(races):
            image(race)
            page(race.path, "race.html", "../../", active="races", race=race, share_race=race,
                 prev_race=races[i - 1] if i else None, next_race=races[i + 1] if i + 1 < len(races) else None)
        if season.scorecard:
            page(season.scorecard_path, "scorecard.html", "../../", active="scorecard", season=season)
    for driver in site.drivers:
        page(driver.path, "driver.html", "../../", active="drivers", driver=driver)


def _standalone(template: str, scorecard_path: str | None, **context) -> str:
    env = environment()
    env.globals["scorecard_path"] = scorecard_path
    return render_page(env, template, SITE_URL,
                       inline_css=(STATIC_DIR / "site.css").read_text(encoding="utf-8"),
                       inline_js=(STATIC_DIR / "site.js").read_text(encoding="utf-8"), **context)


def standalone_race(season: int, rnd: int) -> str:
    """One race page with CSS and JS inlined, linking back to the live site."""
    pred = pd.read_csv(config.prediction_path(season, rnd, ".csv"))
    entries = processed.load_processed()[0]
    season_entries = entries[entries["Season"] == season]
    race = data.race(season, rnd, pred, season_entries[season_entries["RoundNumber"] == rnd],
                     data.driver_ids(season_entries), market.load_market(season, rnd))
    scorecard_path = f"{season}/scorecard/" if data.scorecard(season) else None
    return _standalone("race.html", scorecard_path, active="races", race=race, share_race=race,
                       prev_race=None, next_race=None)


def standalone_scorecard(season: int) -> str:
    card = data.scorecard(season)
    if card is None:
        raise SystemExit(f"No scored predictions for {season} yet.")
    return _standalone("scorecard.html", f"{season}/scorecard/", active="scorecard",
                       season=data.Season(season, [], scorecard=card))

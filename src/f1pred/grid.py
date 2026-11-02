"""Starting grid for an upcoming race: official F1 first, OpenF1 second, quali order otherwise."""
from __future__ import annotations

import pandas as pd
import requests

from f1pred import official

OPENF1 = "https://api.openf1.org/v1"

LABELS = {
    "official": "Starting grid: official (formula1.com)",
    "openf1": "Starting grid: official (via OpenF1)",
    "manual": "Starting grid: quali order with manual overrides",
    "provisional": "Starting grid: provisional (quali order, penalties not out yet)",
}


def grid_from_table(table: pd.DataFrame) -> dict[str, int]:
    """Driver code -> grid slot; a non-numeric slot means a pit lane start (0)."""
    pos = pd.to_numeric(table["Pos"], errors="coerce").fillna(0).astype(int)
    return dict(zip(table["Abbreviation"], pos))


def official_grid(season: int, country: str, location: str, event_name: str) -> dict[str, int] | None:
    try:
        path = official.event_path(season, country, location, event_name)
        return grid_from_table(official.parse_table(official._get(f"{official.BASE}{path}/starting-grid")))
    except (requests.RequestException, ValueError, KeyError):
        return None


def _openf1(endpoint: str, **params) -> list[dict]:
    resp = requests.get(f"{OPENF1}/{endpoint}", params=params, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json()


def openf1_grid(season: int, location: str) -> dict[str, int] | None:
    """OpenF1 keys the race grid by the qualifying session."""
    try:
        sessions = [s for s in _openf1("sessions", year=season, session_name="Qualifying")
                    if official._norm(s["location"]) == official._norm(location)]
        if not sessions:
            return None
        key = sessions[-1]["session_key"]
        rows = _openf1("starting_grid", session_key=key)
        codes = {d["driver_number"]: d["name_acronym"] for d in _openf1("drivers", session_key=key)}
        grid = {codes[r["driver_number"]]: int(r["position"] or 0) for r in rows if r["driver_number"] in codes}
        return grid or None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def fetch(season: int, country: str, location: str, event_name: str) -> tuple[dict[str, int], str]:
    grid = official_grid(season, country, location, event_name)
    if grid:
        return grid, "official"
    grid = openf1_grid(season, location)
    if grid:
        return grid, "openf1"
    return {}, "provisional"

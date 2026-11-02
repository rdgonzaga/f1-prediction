"""Results-only fallback from formula1.com's official results pages, used when live timing is down."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from html.parser import HTMLParser

import numpy as np
import pandas as pd
import requests

from f1pred import config

BASE = "https://www.formula1.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}
JOLPICA = "https://api.jolpi.ca/ergast/f1"

# Session code -> (results page, grid page or None)
PAGES = {
    "R": ("race-result", "starting-grid"),
    "S": ("sprint-results", "sprint-grid"),
    "Q": ("qualifying", None),
    "SQ": ("sprint-qualifying", None),
}

IDENTITY_COLS = ["DriverNumber", "BroadcastName", "Abbreviation", "DriverId", "TeamName", "TeamColor",
                 "TeamId", "FirstName", "LastName", "FullName", "HeadshotUrl", "CountryCode"]
RESULT_COLS = IDENTITY_COLS + ["Position", "ClassifiedPosition", "GridPosition", "Status", "Points", "Laps",
                               "Q1Seconds", "Q2Seconds", "Q3Seconds", "TimeSeconds"]


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_table = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self._in_table = False
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append("|".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None and data.strip():
            self._cell.append(data.strip())


def parse_table(html: str) -> pd.DataFrame:
    parser = _TableParser()
    parser.feed(html)
    if len(parser.rows) < 2:
        raise ValueError("no results table on the page")
    header, *body = parser.rows
    df = pd.DataFrame(body, columns=[h.rstrip(".") for h in header])
    names = df.pop("Driver").str.split("|")
    df["FirstName"] = names.str[0]
    df["LastName"] = names.str[1]
    df["Abbreviation"] = names.str[-1]
    return df


def to_seconds(text: str) -> float:
    text = (text or "").strip().lstrip("+").rstrip("s")
    if not re.fullmatch(r"[\d:.]+", text):
        return np.nan
    total = 0.0
    for part in text.split(":"):
        total = total * 60 + float(part)
    return round(total, 3)


def _get(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


@lru_cache(maxsize=None)
def event_links(season: int) -> tuple[str, ...]:
    html = _get(f"{BASE}/en/results/{season}/races")
    links = re.findall(rf"/en/results/{season}/races/\d+/[a-z0-9-]+/race-result", html)
    return tuple(dict.fromkeys(link.rsplit("/", 1)[0] for link in links))


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


COUNTRY_ALIASES = {"united_kingdom": "great_britain", "united_arab_emirates": "abu_dhabi"}


def _match_score(slug: str, country: str, location: str, event_name: str) -> int:
    slug = _norm(slug)
    specific = [_norm(location), _norm(re.sub(r"grand prix", "", event_name, flags=re.I))]
    if any(n and (slug in n or n in slug) for n in specific):
        return 2
    country = _norm(country)
    return 1 if slug in (country, COUNTRY_ALIASES.get(country)) else 0


def event_path(season: int, country: str, location: str, event_name: str) -> str:
    """The event's results page, matched by name so a reordered calendar can't pick the wrong race."""
    scored = [(_match_score(link.rsplit("/", 1)[-1], country, location, event_name), link)
              for link in event_links(season)]
    best = max((s for s, _ in scored), default=0)
    matches = [link for s, link in scored if s == best]
    if best == 0:
        raise ValueError(f"no official results page matches {season} {event_name}")
    if len(matches) > 1:
        raise ValueError(f"several official results pages match {season} {event_name}: {matches}")
    return matches[0]


def _status(pos: str, time_text: str) -> tuple[str, str]:
    time_text = time_text.upper()
    if pos == "DQ":
        return "D", "Disqualified"
    if time_text == "DNS":
        return "W", "Did not start"
    if time_text == "DNF":
        return (pos if pos.isdigit() else "R"), "Retired"
    if not pos.isdigit():
        return "N", "Not classified"
    return pos, ("Lapped" if "LAP" in time_text else "Finished")


def build_results(results: pd.DataFrame, grid: pd.DataFrame | None, code: str) -> pd.DataFrame:
    out = pd.DataFrame({
        "DriverNumber": results["No"],
        "Abbreviation": results["Abbreviation"],
        "TeamName": results["Team"],
        "FirstName": results["FirstName"],
        "LastName": results["LastName"],
    })
    out["FullName"] = out["FirstName"] + " " + out["LastName"]
    out["Position"] = np.arange(1, len(out) + 1, dtype=float)

    if code in ("Q", "SQ"):
        out["ClassifiedPosition"] = ""
        out["Status"] = ""
        out["Points"] = np.nan
        out["Laps"] = np.nan
        out["TimeSeconds"] = np.nan
        dq = results["Pos"].eq("DQ")
        for q in ("Q1", "Q2", "Q3"):
            out[f"{q}Seconds"] = results[q].map(to_seconds).where(~dq) if q in results else np.nan
        out["GridPosition"] = np.nan
        return out

    status = [_status(p, t) for p, t in zip(results["Pos"], results["Time / Retired"])]
    out["ClassifiedPosition"] = [s[0] for s in status]
    out["Status"] = [s[1] for s in status]
    out["Points"] = pd.to_numeric(results["Pts"], errors="coerce")
    out["Laps"] = pd.to_numeric(results["Laps"], errors="coerce")
    times = results["Time / Retired"].map(to_seconds)
    out["TimeSeconds"] = times.where(out["Status"].eq("Finished"))
    for q in ("Q1", "Q2", "Q3"):
        out[f"{q}Seconds"] = np.nan
    if grid is not None:
        grid_pos = dict(zip(grid["No"], pd.to_numeric(grid["Pos"], errors="coerce")))
        out["GridPosition"] = out["DriverNumber"].map(grid_pos).astype(float)
    else:
        out["GridPosition"] = np.nan
    return out


def known_identities() -> pd.DataFrame:
    """Latest identity columns per driver and team from results already saved."""
    frames = []
    for path in sorted(config.RAW_DIR.glob("*/R*_*_results.parquet")):
        df = pd.read_parquet(path)
        frames.append(df[[c for c in IDENTITY_COLS if c in df.columns]].assign(
            _order=int(path.parent.name) * 100 + int(path.stem.split("_")[0][1:])))
    if not frames:
        return pd.DataFrame(columns=IDENTITY_COLS)
    return pd.concat(frames, ignore_index=True).sort_values("_order")


@lru_cache(maxsize=None)
def jolpica_driver_ids(season: int) -> dict[str, str]:
    try:
        resp = requests.get(f"{JOLPICA}/{season}/drivers.json?limit=100", timeout=30)
        resp.raise_for_status()
        drivers = resp.json()["MRData"]["DriverTable"]["Drivers"]
    except (requests.RequestException, KeyError, ValueError):
        return {}
    return {d["code"]: d["driverId"] for d in drivers if d.get("code")}


def fill_identity(out: pd.DataFrame, season: int, known: pd.DataFrame | None = None) -> pd.DataFrame:
    known = known_identities() if known is None else known
    out = out.copy()
    drivers = known.dropna(subset=["Abbreviation"]).drop_duplicates("Abbreviation", keep="last").set_index("Abbreviation")
    teams = known.dropna(subset=["TeamName"]).drop_duplicates("TeamName", keep="last").set_index("TeamName")

    for col in ("DriverId", "BroadcastName", "HeadshotUrl", "CountryCode"):
        out[col] = out["Abbreviation"].map(drivers[col]) if col in drivers else np.nan
    for col in ("TeamId", "TeamColor"):
        out[col] = out["TeamName"].map(teams[col]) if col in teams else np.nan

    missing = out["DriverId"].isna()
    if missing.any():
        out.loc[missing, "DriverId"] = out.loc[missing, "Abbreviation"].map(jolpica_driver_ids(season))
        still = out["DriverId"].isna()
        out.loc[still, "DriverId"] = out.loc[still, "LastName"].map(_norm)
    out["TeamId"] = out["TeamId"].fillna(out["TeamName"].map(_norm))
    out["BroadcastName"] = out["BroadcastName"].fillna(
        out["FirstName"].str[0] + " " + out["LastName"].str.upper())
    return out


def session_results(season: int, code: str, country: str, location: str, event_name: str) -> pd.DataFrame:
    if code not in PAGES:
        raise ValueError(f"no official fallback for {code} sessions")
    path = event_path(season, country, location, event_name)
    results_page, grid_page = PAGES[code]
    results = parse_table(_get(f"{BASE}{path}/{results_page}"))
    grid = parse_table(_get(f"{BASE}{path}/{grid_page}")) if grid_page else None
    out = fill_identity(build_results(results, grid, code), season)
    return out[RESULT_COLS]

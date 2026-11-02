"""Polymarket race-winner odds from an hour before the start, as a baseline for our win chances."""
from __future__ import annotations

import json
import re
import unicodedata

import fastf1
import pandas as pd
import requests

from f1pred import build, config, fetch

EVENTS_URL = "https://gamma-api.polymarket.com/events"
HISTORY_URL = "https://clob.polymarket.com/prices-history"
HEADERS = {"User-Agent": "f1-prediction"}
LEAD = pd.Timedelta(hours=1)
MIN_PRICE = 0.001
MAX_DATE_GAP_DAYS = 2


def market_path(season: int, rnd: int):
    return config.PREDICTIONS_DIR / str(season) / f"round_{rnd:02d}" / "polymarket.csv"


def load_market(season: int, rnd: int) -> pd.DataFrame | None:
    path = market_path(season, rnd)
    return pd.read_csv(path) if path.exists() else None


def winner_events(season: int) -> dict[pd.Timestamp, dict]:
    """Race-winner events for a season keyed by the date in their slug."""
    pattern = re.compile(rf"^f1-.*-grand-prix-winner-({season}-\d\d-\d\d)$")
    found, offset = {}, 0
    while True:
        page = requests.get(EVENTS_URL, headers=HEADERS, timeout=30, params={
            "tag_slug": "formula1", "limit": 100, "offset": offset, "order": "endDate", "ascending": "false",
            "end_date_min": f"{season}-01-01T00:00:00Z", "end_date_max": f"{season + 1}-01-31T00:00:00Z",
        }).json()
        for event in page:
            match = pattern.match(event["slug"])
            if match:
                found.setdefault(pd.Timestamp(match.group(1)), event)
        if len(page) < 100:
            return found
        offset += 100


def race_starts(season: int) -> pd.DataFrame:
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    rows = []
    for _, event in schedule[schedule["RoundNumber"] > 0].iterrows():
        for i in range(1, 6):
            if event.get(f"Session{i}") == "Race":
                rows.append({"RoundNumber": int(event["RoundNumber"]),
                             "RaceDate": pd.Timestamp(event[f"Session{i}Date"]).tz_localize(None).normalize(),
                             "StartUTC": pd.Timestamp(event[f"Session{i}DateUtc"]).tz_localize("UTC")})
    return pd.DataFrame(rows)


def event_for(events: dict[pd.Timestamp, dict], race_date: pd.Timestamp) -> dict | None:
    """Slug dates drift a day from the race (Australia 2026 is dated Saturday), so take the nearest."""
    near = [d for d in events if abs((d - race_date).days) <= MAX_DATE_GAP_DAYS]
    return events[min(near, key=lambda d: abs(d - race_date))] if near else None


def price_at(token: str, at: pd.Timestamp) -> float | None:
    end = int(at.timestamp())
    history = requests.get(HISTORY_URL, headers=HEADERS, timeout=30, params={
        "market": token, "startTs": end - 12 * 3600, "endTs": end, "fidelity": 10,
    }).json().get("history", [])
    return float(history[-1]["p"]) if history else None


def name_key(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.split(r"[\s_]+", ascii_name.strip())[-1]


def match_drivers(prices: pd.DataFrame, entries: pd.DataFrame) -> pd.DataFrame:
    """Join market names to the race's drivers by surname and renormalise to 100%."""
    keys = pd.Series(entries["Abbreviation"].to_numpy(), index=entries["DriverId"].map(name_key))
    keys = keys[~keys.index.duplicated(keep=False)]
    prices = prices.assign(Abbreviation=prices["Name"].map(name_key).map(keys))
    lost = prices[prices["Abbreviation"].isna() & prices["Price"].gt(0.01)]
    if not lost.empty:
        print(f"  unmatched market names: {', '.join(lost['Name'])}")
    prices = prices.dropna(subset=["Abbreviation"])
    out = entries[["Abbreviation"]].merge(prices, on="Abbreviation", how="left")
    out["Price"] = out["Price"].fillna(0).clip(lower=MIN_PRICE)
    out["MarketWinPct"] = out["Price"] / out["Price"].sum() * 100
    return out


def snapshot(event: dict, at: pd.Timestamp) -> pd.DataFrame:
    rows = [{"Name": m["groupItemTitle"], "Price": price_at(json.loads(m["clobTokenIds"])[0], at)}
            for m in event["markets"]]
    return pd.DataFrame(rows)


def run(season: int, rounds: list[int] | None = None, refresh: bool = False) -> None:
    fetch.enable_cache()
    entries = build.load_processed()[0]
    entries = entries[entries["Season"] == season]
    starts = race_starts(season)
    if rounds:
        starts = starts[starts["RoundNumber"].isin(rounds)]
    now = pd.Timestamp.now(tz="UTC")
    events = winner_events(season)
    for _, race in starts.iterrows():
        rnd, at = int(race["RoundNumber"]), race["StartUTC"] - LEAD
        path = market_path(season, rnd)
        if at > now or (path.exists() and not refresh):
            continue
        event = event_for(events, race["RaceDate"])
        drivers = entries[entries["RoundNumber"] == rnd]
        if event is None or drivers.empty:
            print(f"{season} R{rnd:02d}: no {'market' if event is None else 'entry list'}, skipped")
            continue
        out = match_drivers(snapshot(event, at), drivers)
        path.parent.mkdir(parents=True, exist_ok=True)
        out.assign(SnapshotUTC=at.isoformat(), Slug=event["slug"]).to_csv(path, index=False)
        top = out.nlargest(3, "MarketWinPct")
        print(f"{season} R{rnd:02d}: saved, " + ", ".join(f"{a} {p:.0f}%" for a, p in zip(top["Abbreviation"], top["MarketWinPct"])))

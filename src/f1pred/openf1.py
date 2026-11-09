from __future__ import annotations

import unicodedata
from functools import lru_cache

import pandas as pd
import requests

API = "https://api.openf1.org/v1"
SESSION_NAMES = {"FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3", "SQ": "Sprint Qualifying",
                 "S": "Sprint", "Q": "Qualifying", "R": "Race"}


def _get(path: str, **params) -> list[dict]:
    resp = requests.get(f"{API}/{path}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in text if ch.isalnum())


@lru_cache(maxsize=None)
def meetings(season: int) -> tuple[dict, ...]:
    return tuple(_get("meetings", year=season))


def meeting_key(season: int, country: str, location: str, event_name: str) -> int:
    targets = {_norm(country), _norm(location)}
    for m in meetings(season):
        names = {_norm(m["country_name"]), _norm(m["location"]), _norm(m["circuit_short_name"])}
        if targets & names:
            return m["meeting_key"]
    raise LookupError(f"OpenF1 meeting not found for {season} {event_name}")


def session_weather(season: int, code: str, country: str, location: str, event_name: str) -> pd.DataFrame:
    key = meeting_key(season, country, location, event_name)
    sessions = _get("sessions", meeting_key=key, session_name=SESSION_NAMES[code])
    if not sessions:
        raise LookupError(f"OpenF1 session {code} not found for {event_name}")
    rows = _get("weather", session_key=sessions[0]["session_key"])
    if not rows:
        raise LookupError(f"OpenF1 has no weather for {event_name} {code}")
    df = pd.DataFrame(rows)
    start = pd.to_datetime(sessions[0]["date_start"], format="ISO8601")
    return pd.DataFrame({
        "AirTemp": df["air_temperature"].astype(float),
        "Humidity": df["humidity"].astype(float),
        "Pressure": df["pressure"].astype(float),
        "Rainfall": df["rainfall"].astype(float) > 0,
        "TrackTemp": df["track_temperature"].astype(float),
        "WindDirection": df["wind_direction"].astype("int64"),
        "WindSpeed": df["wind_speed"].astype(float),
        "TimeSeconds": (pd.to_datetime(df["date"], format="ISO8601") - start).dt.total_seconds(),
    })

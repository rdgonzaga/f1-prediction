import pandas as pd
import pytest

from f1pred import market


def test_name_key_matches_market_names_to_driver_ids():
    assert market.name_key("Kimi Antonelli") == market.name_key("antonelli")
    assert market.name_key("Max Verstappen") == market.name_key("max_verstappen")
    assert market.name_key("Nico Hülkenberg") == market.name_key("hulkenberg")


def test_match_drivers_drops_non_entrants_and_removes_vig():
    entries = pd.DataFrame({"Abbreviation": ["VER", "HAM", "STR"], "DriverId": ["max_verstappen", "hamilton", "stroll"]})
    prices = pd.DataFrame({"Name": ["Max Verstappen", "Lewis Hamilton", "Felipe Drugovich"],
                           "Price": [0.66, 0.44, 0.02]})
    out = market.match_drivers(prices, entries).set_index("Abbreviation")
    assert out["MarketWinPct"].sum() == pytest.approx(100)
    assert out.loc["VER", "MarketWinPct"] > out.loc["HAM", "MarketWinPct"] > out.loc["STR", "MarketWinPct"] > 0


def test_event_for_takes_nearest_slug_date():
    events = {pd.Timestamp("2026-03-07"): "aus", pd.Timestamp("2026-03-15"): "chn"}
    assert market.event_for(events, pd.Timestamp("2026-03-08")) == "aus"
    assert market.event_for(events, pd.Timestamp("2026-03-11")) is None

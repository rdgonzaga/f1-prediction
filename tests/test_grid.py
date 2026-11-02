import numpy as np
import pandas as pd
import requests

from f1pred import grid, predict


def race(codes, grid_pos=None):
    return pd.DataFrame({
        "Abbreviation": codes,
        "QPosition": np.arange(1.0, len(codes) + 1),
        "GridPosition": grid_pos if grid_pos is not None else [np.nan] * len(codes),
    })


def test_table_maps_codes_and_pit_lane():
    table = pd.DataFrame({"Pos": ["1", "2", "PL"], "Abbreviation": ["VER", "LEC", "RUS"]})
    assert grid.grid_from_table(table) == {"VER": 1, "LEC": 2, "RUS": 0}


def test_official_wins_then_openf1_then_provisional(monkeypatch):
    monkeypatch.setattr(grid, "official_grid", lambda *a: {"VER": 1})
    monkeypatch.setattr(grid, "openf1_grid", lambda *a: {"LEC": 1})
    assert grid.fetch(2026, "Mexico", "Mexico City", "Mexico City Grand Prix") == ({"VER": 1}, "official")
    monkeypatch.setattr(grid, "official_grid", lambda *a: None)
    assert grid.fetch(2026, "Mexico", "Mexico City", "Mexico City Grand Prix") == ({"LEC": 1}, "openf1")
    monkeypatch.setattr(grid, "openf1_grid", lambda *a: None)
    assert grid.fetch(2026, "Mexico", "Mexico City", "Mexico City Grand Prix") == ({}, "provisional")


def test_official_grid_returns_none_when_the_page_is_empty(monkeypatch):
    monkeypatch.setattr(grid.official, "event_path", lambda *a: "/en/results/2026/races/1299/brazil")
    monkeypatch.setattr(grid.official, "_get", lambda url: "<html>no grid yet</html>")
    assert grid.official_grid(2026, "Brazil", "São Paulo", "São Paulo Grand Prix") is None


def test_official_grid_returns_none_when_offline(monkeypatch):
    def boom(*a):
        raise requests.ConnectionError
    monkeypatch.setattr(grid.official, "event_path", boom)
    assert grid.official_grid(2026, "Brazil", "São Paulo", "São Paulo Grand Prix") is None


def test_fetched_grid_replaces_quali_order(monkeypatch):
    # Mexico 2026: LAW qualified 8th but was disqualified and started last.
    monkeypatch.setattr(predict.fastf1, "get_event", lambda s, r: {
        "Country": "Mexico", "Location": "Mexico City", "EventName": "Mexico City Grand Prix"})
    monkeypatch.setattr(predict.grid, "fetch", lambda *a: ({"HAM": 1, "RUS": 2, "LAW": 3}, "official"))
    positions, source = predict.starting_grid(race(["LAW", "HAM", "RUS"]), 2026, 19, {}, set(), {})
    assert list(positions) == [3.0, 1.0, 2.0] and source == "official"


def test_no_grid_yet_keeps_quali_order(monkeypatch):
    monkeypatch.setattr(predict.fastf1, "get_event", lambda s, r: {
        "Country": "Brazil", "Location": "São Paulo", "EventName": "São Paulo Grand Prix"})
    monkeypatch.setattr(predict.grid, "fetch", lambda *a: ({}, "provisional"))
    positions, source = predict.starting_grid(race(["VER", "LEC"]), 2026, 20, {}, set(), {})
    assert positions.isna().all() and source == "provisional"


def test_manual_overrides_skip_the_fetch(monkeypatch):
    monkeypatch.setattr(predict.grid, "fetch", lambda *a: (_ for _ in ()).throw(AssertionError("fetched")))
    positions, source = predict.starting_grid(race(["VER", "LEC", "RUS"]), 2026, 17, {"VER": 5}, set(), {})
    assert list(positions) == [3.0, 1.0, 2.0] and source == "manual"


def test_race_with_a_result_already_has_its_grid(monkeypatch):
    monkeypatch.setattr(predict.grid, "fetch", lambda *a: (_ for _ in ()).throw(AssertionError("fetched")))
    positions, source = predict.starting_grid(race(["VER", "LEC"], [2.0, 1.0]), 2026, 17, {}, set(), {})
    assert list(positions) == [2.0, 1.0] and source == "official"

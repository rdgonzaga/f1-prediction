import numpy as np
import pandas as pd

from f1pred.build import build_entries, data_checks, normalize_location


def entry_rows(season, rnd, n, event, location, quali=True, result=True):
    return pd.DataFrame({
        "Season": season, "RoundNumber": rnd, "EventName": event, "Location": location,
        "DriverId": [f"d{i}" for i in range(n)],
        "QPosition": np.arange(1, n + 1) if quali else np.nan,
        "FinishPosition": np.arange(1, n + 1) if result else np.nan,
    })


def test_data_checks_flag_incomplete_races_and_venue_changes():
    entries = pd.concat([
        entry_rows(2025, 1, 20, "Belgian Grand Prix", "barcelona"),
        entry_rows(2026, 1, 10, "Belgian Grand Prix", "madrid", quali=False, result=False),
        entry_rows(2026, 2, 20, "Next Grand Prix", "y", result=False),
    ], ignore_index=True)
    conditions = pd.DataFrame({"Season": [2025, 2026, 2026], "RoundNumber": [1, 1, 2]})
    laps = pd.DataFrame({"Season": [2025, 2026], "RoundNumber": [1, 1]})

    issues = data_checks(entries, conditions, laps)

    assert "2026 R01 Belgian Grand Prix: only 10 entries" in issues
    assert "2026 R01 Belgian Grand Prix: no qualifying results" in issues
    assert "2026 R01 Belgian Grand Prix: no race results" in issues
    assert "2026 R02 Next Grand Prix: no practice or sprint laps" in issues
    assert not any("R02 Next Grand Prix: no race results" in i for i in issues)
    assert any(i.startswith("Belgian Grand Prix: held at barcelona, madrid") for i in issues)
    assert not any(i.startswith("2025 R01") for i in issues)


def test_location_aliases_and_accents_match_across_seasons():
    assert normalize_location("Miami Gardens") == normalize_location("Miami")
    assert normalize_location("Monte Carlo") == normalize_location("Monaco")
    assert normalize_location("Montréal") == "montreal"


def result_row(session, number, driver_id, position, grid=np.nan):
    return {
        "Season": 2026, "RoundNumber": 1, "EventName": "Australian Grand Prix",
        "EventFormat": "conventional", "Location": "Melbourne", "SessionCode": session,
        "DriverNumber": number, "DriverId": driver_id, "Abbreviation": number.upper(),
        "TeamId": "nan" if driver_id == "nan" else "team", "TeamName": "Team",
        "Position": position, "GridPosition": grid, "ClassifiedPosition": str(int(position)),
        "Status": "Finished", "Points": 0.0, "Laps": 58.0,
        "Q1Seconds": np.nan if driver_id == "nan" else 80.0, "Q2Seconds": np.nan, "Q3Seconds": np.nan,
    }


def test_data_checks_skip_confirmed_venue_changes():
    entries = pd.concat([
        entry_rows(2025, 1, 20, "Spanish Grand Prix", "barcelona"),
        entry_rows(2026, 1, 20, "Spanish Grand Prix", "madrid"),
    ], ignore_index=True)
    races = pd.DataFrame({"Season": [2025, 2026], "RoundNumber": [1, 1]})
    assert data_checks(entries, races, races) == []


def test_driver_missing_id_in_quali_is_not_duplicated():
    results = pd.DataFrame([
        result_row("Q", "a", "alpha", 1.0),
        result_row("Q", "b", "nan", 2.0),
        result_row("R", "a", "alpha", 2.0, grid=1.0),
        result_row("R", "b", "bravo", 1.0, grid=2.0),
    ])
    entries = build_entries(results)

    assert len(entries) == 2
    assert set(entries["DriverId"]) == {"alpha", "bravo"}
    bravo = entries.set_index("DriverId").loc["bravo"]
    assert bravo["QPosition"] == 2.0
    assert bravo["FinishPosition"] == 1.0
    assert bravo["TeamId"] == "team"

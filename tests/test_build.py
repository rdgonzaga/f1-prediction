import numpy as np
import pandas as pd

from f1pred.build import build_entries


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

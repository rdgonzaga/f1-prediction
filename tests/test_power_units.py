import pandas as pd

from f1pred import build

KNOWN_SUPPLIERS = {"mercedes", "ferrari", "renault", "honda_rbpt", "honda", "red_bull_ford", "audi"}


def test_power_unit_table_is_complete_and_consistent():
    pu = build.load_power_units()
    assert not pu.duplicated(["Season", "TeamId"]).any()
    assert set(pu["PowerUnit"]) <= KNOWN_SUPPLIERS
    assert pu.groupby("Season").size().to_dict() == {2022: 10, 2023: 10, 2024: 10, 2025: 10, 2026: 11}


def test_power_unit_spot_checks():
    pu = build.load_power_units().set_index(["Season", "TeamId"])["PowerUnit"]
    assert pu[(2022, "alfa")] == "ferrari"
    assert pu[(2023, "alphatauri")] == "honda_rbpt"
    assert pu[(2024, "rb")] == "honda_rbpt"
    assert pu[(2025, "alpine")] == "renault"
    assert pu[(2025, "aston_martin")] == "mercedes"
    assert pu[(2026, "alpine")] == "mercedes"
    assert pu[(2026, "aston_martin")] == "honda"
    assert pu[(2026, "cadillac")] == "ferrari"
    assert pu[(2026, "red_bull")] == "red_bull_ford"
    assert pu[(2026, "audi")] == "audi"


def test_data_checks_flag_team_without_power_unit():
    entries = pd.DataFrame({
        "Season": [2027], "RoundNumber": [1], "EventName": ["X"], "Location": ["x"],
        "DriverId": ["d"], "TeamId": ["newteam"], "QPosition": [1.0], "FinishPosition": [1.0],
    })
    races = pd.DataFrame({"Season": [2027], "RoundNumber": [1]})
    issues = build.data_checks(entries, races, races, build.load_power_units())
    assert "2027 newteam: no power unit in power_units.csv" in issues

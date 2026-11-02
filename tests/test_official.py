import numpy as np
import pandas as pd
import pytest

from f1pred import official


def _driver(first, last, code):
    return f"<td><span>{first}</span><span>{last}</span><span>{code}</span></td>"


def _table(header, rows):
    head = "".join(f"<th>{h}</th>" for h in header)
    body = ""
    for pos, no, drv, team, *rest in rows:
        cells = f"<td>{pos}</td><td>{no}</td>{_driver(*drv)}<td>{team}</td>"
        body += "<tr>" + cells + "".join(f"<td>{c}</td>" for c in rest) + "</tr>"
    return f"<html><body><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></body></html>"


RACE_HTML = _table(["Pos.", "No.", "Driver", "Team", "Laps", "Time / Retired", "Pts."], [
    ("1", "3", ("Max", "Verstappen", "VER"), "Red Bull Racing", "71", "2:20:28.772", "25"),
    ("2", "44", ("Lewis", "Hamilton", "HAM"), "Ferrari", "71", "+0.799s", "18"),
    ("3", "55", ("Carlos", "Sainz", "SAI"), "Williams", "70", "+1 lap", "15"),
    ("4", "14", ("Fernando", "Alonso", "ALO"), "Aston Martin", "65", "DNF", "12"),
    ("NC", "18", ("Lance", "Stroll", "STR"), "Aston Martin", "5", "DNF", "0"),
    ("NC", "23", ("Alexander", "Albon", "ALB"), "Williams", "0", "DNS", "0"),
    ("DQ", "30", ("Liam", "Lawson", "LAW"), "Racing Bulls", "71", "DSQ", "0"),
])

GRID_HTML = _table(["Pos.", "No.", "Driver", "Team", "Time"], [
    ("1", "44", ("Lewis", "Hamilton", "HAM"), "Ferrari", "1:16.514"),
    ("2", "3", ("Max", "Verstappen", "VER"), "Red Bull Racing", "1:16.600"),
    ("3", "55", ("Carlos", "Sainz", "SAI"), "Williams", ""),
    ("4", "14", ("Fernando", "Alonso", "ALO"), "Aston Martin", ""),
    ("5", "18", ("Lance", "Stroll", "STR"), "Aston Martin", ""),
    ("6", "23", ("Alexander", "Albon", "ALB"), "Williams", ""),
    ("7", "30", ("Liam", "Lawson", "LAW"), "Racing Bulls", ""),
])

QUALI_HTML = _table(["Pos.", "No.", "Driver", "Team", "Q1", "Q2", "Q3", "Laps"], [
    ("1", "44", ("Lewis", "Hamilton", "HAM"), "Ferrari", "1:17.341", "1:16.953", "1:16.514", "20"),
    ("2", "77", ("Valtteri", "Bottas", "BOT"), "Cadillac", "1:19.852", "", "", "9"),
    ("DQ", "30", ("Liam", "Lawson", "LAW"), "Racing Bulls", "", "1:17.207", "1:17.029", "0"),
])


def test_parse_table_splits_driver_cell():
    df = official.parse_table(RACE_HTML)
    assert df.loc[0, ["Pos", "No", "Abbreviation", "FirstName", "LastName"]].tolist() == [
        "1", "3", "VER", "Max", "Verstappen"]
    assert len(df) == 7


def test_to_seconds_handles_totals_gaps_and_text():
    assert official.to_seconds("2:20:28.772") == 8428.772
    assert official.to_seconds("+0.799s") == 0.799
    assert official.to_seconds("1:17.341") == 77.341
    assert np.isnan(official.to_seconds("+1 lap"))
    assert np.isnan(official.to_seconds("DNF"))
    assert np.isnan(official.to_seconds(""))


def test_race_results_status_grid_and_points():
    out = official.build_results(official.parse_table(RACE_HTML), official.parse_table(GRID_HTML), "R")
    rows = out.set_index("Abbreviation")
    assert rows["Position"].tolist() == [1, 2, 3, 4, 5, 6, 7]
    assert rows.loc["VER", ["ClassifiedPosition", "Status", "GridPosition", "Points"]].tolist() == ["1", "Finished", 2.0, 25.0]
    assert rows.loc["SAI", ["ClassifiedPosition", "Status"]].tolist() == ["3", "Lapped"]
    assert rows.loc["ALO", ["ClassifiedPosition", "Status"]].tolist() == ["4", "Retired"]
    assert rows.loc["STR", ["ClassifiedPosition", "Status"]].tolist() == ["R", "Retired"]
    assert rows.loc["ALB", ["ClassifiedPosition", "Status"]].tolist() == ["W", "Did not start"]
    assert rows.loc["LAW", ["ClassifiedPosition", "Status"]].tolist() == ["D", "Disqualified"]
    assert rows.loc["VER", "TimeSeconds"] == 8428.772
    assert rows.loc["HAM", "TimeSeconds"] == 0.799
    assert np.isnan(rows.loc["SAI", "TimeSeconds"])


def test_quali_results_drop_times_for_disqualified_driver():
    out = official.build_results(official.parse_table(QUALI_HTML), None, "Q").set_index("Abbreviation")
    assert out.loc["HAM", ["Q1Seconds", "Q2Seconds", "Q3Seconds"]].tolist() == [77.341, 76.953, 76.514]
    assert np.isnan(out.loc["BOT", "Q2Seconds"])
    assert out.loc["LAW", "Position"] == 3
    assert out.loc["LAW", ["Q1Seconds", "Q2Seconds", "Q3Seconds"]].isna().all()
    assert out["GridPosition"].isna().all()


def test_fill_identity_uses_saved_then_jolpica_then_slug(monkeypatch):
    monkeypatch.setattr(official, "jolpica_driver_ids", lambda season: {"BOT": "bottas"})
    known = pd.DataFrame([
        {"Abbreviation": "HAM", "DriverId": "hamilton", "TeamName": "Ferrari", "TeamId": "ferrari",
         "TeamColor": "ED1131", "BroadcastName": "L HAMILTON", "HeadshotUrl": "", "CountryCode": "GBR"},
    ])
    out = official.build_results(official.parse_table(QUALI_HTML), None, "Q")
    out = official.fill_identity(out, 2026, known).set_index("Abbreviation")
    assert out.loc["HAM", ["DriverId", "TeamId", "TeamColor"]].tolist() == ["hamilton", "ferrari", "ED1131"]
    assert out.loc["BOT", "DriverId"] == "bottas"
    assert out.loc["LAW", ["DriverId", "TeamId", "BroadcastName"]].tolist() == ["lawson", "racing_bulls", "L LAWSON"]


SCHEDULES = {
    2025: [
        ("Australia", "Melbourne", "Australian Grand Prix", "australia"),
        ("China", "Shanghai", "Chinese Grand Prix", "china"),
        ("Japan", "Suzuka", "Japanese Grand Prix", "japan"),
        ("Bahrain", "Sakhir", "Bahrain Grand Prix", "bahrain"),
        ("Saudi Arabia", "Jeddah", "Saudi Arabian Grand Prix", "saudi-arabia"),
        ("United States", "Miami Gardens", "Miami Grand Prix", "miami"),
        ("Italy", "Imola", "Emilia Romagna Grand Prix", "emilia-romagna"),
        ("Monaco", "Monaco", "Monaco Grand Prix", "monaco"),
        ("Spain", "Barcelona", "Spanish Grand Prix", "spain"),
        ("Canada", "Montréal", "Canadian Grand Prix", "canada"),
        ("Austria", "Spielberg", "Austrian Grand Prix", "austria"),
        ("United Kingdom", "Silverstone", "British Grand Prix", "great-britain"),
        ("Belgium", "Spa-Francorchamps", "Belgian Grand Prix", "belgium"),
        ("Hungary", "Budapest", "Hungarian Grand Prix", "hungary"),
        ("Netherlands", "Zandvoort", "Dutch Grand Prix", "netherlands"),
        ("Italy", "Monza", "Italian Grand Prix", "italy"),
        ("Azerbaijan", "Baku", "Azerbaijan Grand Prix", "azerbaijan"),
        ("Singapore", "Marina Bay", "Singapore Grand Prix", "singapore"),
        ("United States", "Austin", "United States Grand Prix", "united-states"),
        ("Mexico", "Mexico City", "Mexico City Grand Prix", "mexico"),
        ("Brazil", "São Paulo", "São Paulo Grand Prix", "brazil"),
        ("United States", "Las Vegas", "Las Vegas Grand Prix", "las-vegas"),
        ("Qatar", "Lusail", "Qatar Grand Prix", "qatar"),
        ("United Arab Emirates", "Yas Island", "Abu Dhabi Grand Prix", "abu-dhabi"),
    ],
    2026: [
        ("Australia", "Melbourne", "Australian Grand Prix", "australia"),
        ("China", "Shanghai", "Chinese Grand Prix", "china"),
        ("Japan", "Suzuka", "Japanese Grand Prix", "japan"),
        ("United States", "Miami Gardens", "Miami Grand Prix", "miami"),
        ("Canada", "Montréal", "Canadian Grand Prix", "canada"),
        ("Monaco", "Monte Carlo", "Monaco Grand Prix", "monaco"),
        ("Spain", "Barcelona", "Barcelona Grand Prix", "barcelona-catalunya"),
        ("Austria", "Spielberg", "Austrian Grand Prix", "austria"),
        ("United Kingdom", "Silverstone", "British Grand Prix", "great-britain"),
        ("Belgium", "Spa-Francorchamps", "Belgian Grand Prix", "belgium"),
        ("Hungary", "Budapest", "Hungarian Grand Prix", "hungary"),
        ("Netherlands", "Zandvoort", "Dutch Grand Prix", "netherlands"),
        ("Italy", "Monza", "Italian Grand Prix", "italy"),
        ("Spain", "Madrid", "Spanish Grand Prix", "spain"),
        ("Azerbaijan", "Baku", "Azerbaijan Grand Prix", "azerbaijan"),
        ("Bahrain", "Kuala Lumpur", "Bahrain Grand Prix", "bahrain"),
        ("Singapore", "Marina Bay", "Singapore Grand Prix", "singapore"),
        ("United States", "Austin", "United States Grand Prix", "united-states"),
        ("Mexico", "Mexico City", "Mexico City Grand Prix", "mexico"),
        ("Brazil", "São Paulo", "São Paulo Grand Prix", "brazil"),
        ("United States", "Las Vegas", "Las Vegas Grand Prix", "las-vegas"),
        ("Qatar", "Lusail", "Qatar Grand Prix", "qatar"),
        ("United Arab Emirates", "Yas Marina", "Abu Dhabi Grand Prix", "abu-dhabi"),
    ],
}


def _links(season, slugs):
    return tuple(f"/en/results/{season}/races/{1000 + i}/{slug}" for i, slug in enumerate(slugs))


@pytest.mark.parametrize("season", sorted(SCHEDULES))
def test_event_path_matches_every_event_by_name_even_when_reordered(monkeypatch, season):
    events = SCHEDULES[season]
    slugs = [e[3] for e in events]
    for order in (slugs, list(reversed(slugs))):
        monkeypatch.setattr(official, "event_links", lambda s, order=order: _links(season, order))
        for country, location, name, slug in events:
            assert official.event_path(season, country, location, name).endswith(f"/{slug}"), name


def test_event_path_refuses_to_guess(monkeypatch):
    monkeypatch.setattr(official, "event_links", lambda s: _links(2027, ["australia", "china"]))
    with pytest.raises(ValueError, match="no official results page"):
        official.event_path(2027, "Japan", "Suzuka", "Japanese Grand Prix")

    monkeypatch.setattr(official, "event_links", lambda s: _links(2027, ["united-states", "united-states"]))
    with pytest.raises(ValueError, match="several"):
        official.event_path(2027, "United States", "Austin", "United States Grand Prix")

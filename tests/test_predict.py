import pandas as pd

from f1pred.predict import headline, markdown_table


def test_markdown_table_and_headline():
    out = pd.DataFrame({
        "PredictedPosition": [1, 2, 3, 4],
        "Abbreviation": ["ANT", "NOR", "VER", "RUS"],
        "WinPct": [59.2, 9.4, 8.2, 7.2],
        "PodiumPct": [90.6, 44.2, 37.6, 42.4],
    })
    table = markdown_table(out).splitlines()
    assert table[0] == "| PredictedPosition | Abbreviation | WinPct | PodiumPct |"
    assert table[1] == "|---|---|---|---|"
    assert table[2] == "| 1 | ANT | 59.2 | 90.6 |"
    assert len(table) == 6
    assert headline(out) == "Favourite: ANT (59% win) | Most likely podium: ANT, NOR, RUS"

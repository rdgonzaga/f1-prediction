import numpy as np
import pandas as pd
import pandas.testing as pdt

from f1pred import dnf
from f1pred.features import OUTCOME_COLS, build_features
from f1pred.probabilities import finish_probabilities
from test_features import make_data


def race_rows(df, season, rnd):
    return df[(df["Season"] == season) & (df["RoundNumber"] == rnd)]


def test_reliability_features_ignore_target_race_outcome():
    entries, laps, conditions = make_data()
    full = dnf.add_reliability_features(build_features(entries, laps, conditions))

    blind_entries = entries.copy()
    target = (blind_entries["Season"] == 2026) & (blind_entries["RoundNumber"] == 3)
    blind_entries.loc[target, OUTCOME_COLS] = np.nan
    blind = dnf.add_reliability_features(build_features(blind_entries, laps, conditions))

    cols = ["DriverId", "TeamDnfSeason", "FieldDnfLast10"]
    pick = lambda df: race_rows(df, 2026, 3)[cols].sort_values("DriverId").reset_index(drop=True)
    pdt.assert_frame_equal(pick(full), pick(blind))


def test_dnf_probabilities_are_valid_and_keep_index():
    feats = dnf.add_reliability_features(build_features(*make_data()))
    race = race_rows(feats, 2026, 4)
    p = dnf.race_dnf_probability(feats, int(race["RaceIdx"].iloc[0]), race)
    assert len(p) == len(race)
    assert ((p > 0) & (p < 1)).all()


def test_certain_dnf_goes_to_back_and_zero_dnf_matches_plain_simulation():
    scores = pd.Series([3.0, 0.0, -1.0], index=list("abc"))
    certain = finish_probabilities(scores, 1.0, dnf_prob=[1.0, 0.0, 0.0])
    assert certain.loc["a", "WinPct"] == 0
    assert certain.loc["a", "ExpectedPosition"] == 3
    assert certain.loc["a", "DnfPct"] == 100

    none = finish_probabilities(scores, 1.0, dnf_prob=[0.0, 0.0, 0.0])
    pdt.assert_frame_equal(none.drop(columns="DnfPct"), finish_probabilities(scores, 1.0))

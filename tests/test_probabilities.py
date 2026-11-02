import numpy as np
import pandas as pd
import pytest

from f1pred import probabilities as pb


def test_probabilities_sum_and_follow_scores():
    scores = pd.Series([2.0, 1.0, 0.0, -1.0, -2.0], index=list("abcde"))
    p = pb.finish_probabilities(scores, temperature=1.0)
    assert p["WinPct"].sum() == pytest.approx(100)
    assert p["PodiumPct"].sum() == pytest.approx(300)
    assert p["WinPct"].is_monotonic_decreasing
    assert p["ExpectedPosition"].is_monotonic_increasing


def test_log_likelihood_matches_brute_force():
    s = np.array([1.0, 0.5, -0.2])
    t = 0.7
    w = np.exp(s / t)
    expected = np.log(w[1] / w.sum()) + np.log(w[0] / (w[0] + w[2]))
    assert pb.order_log_likelihood(s, [2, 1, 3], t) == pytest.approx(expected)


def test_top_k_log_likelihood_only_scores_first_picks():
    s = np.array([1.0, 0.5, -0.2, 0.3])
    t = 1.3
    w = np.exp(s / t)
    finish = [2, 1, 4, 3]
    first_pick = np.log(w[1] / w.sum())
    second_pick = np.log(w[0] / (w.sum() - w[1]))
    assert pb.order_log_likelihood(s, finish, t, top_k=1) == pytest.approx(first_pick)
    assert pb.order_log_likelihood(s, finish, t, top_k=2) == pytest.approx(first_pick + second_pick)
    assert pb.order_log_likelihood(s, finish, t, top_k=None) == pytest.approx(pb.order_log_likelihood(s, finish, t))


def test_fit_temperature_recovers_noise_level():
    rng = np.random.default_rng(1)
    races = []
    for i in range(300):
        scores = pd.Series(rng.normal(size=10) * 2)
        finish = pb.simulate_positions(scores, temperature=2.0, n_sims=1, seed=i)[0]
        races.append(pd.DataFrame({"Score": scores, "FinishPosition": finish.astype(float)}))
    assert 1.4 < pb.fit_temperature(races) < 2.9


def test_rolling_probabilities_skips_warmup_and_fits_on_recent_window(monkeypatch):
    seen = []
    monkeypatch.setattr(pb, "fit_temperature", lambda races, *a, **k: seen.append(len(races)) or 1.0)
    races = [pd.DataFrame({"Score": [1.0, 0.0], "FinishPosition": [1.0, 2.0], "RaceIdx": [i, i]})
             for i in range(pb.CALIBRATION_WINDOW + 3)]
    out = pb.rolling_probabilities(races, n_sims=100, warmup=3)
    assert [int(r["RaceIdx"].iloc[0]) for r in out] == list(range(3, len(races)))
    assert seen[-1] == pb.CALIBRATION_WINDOW

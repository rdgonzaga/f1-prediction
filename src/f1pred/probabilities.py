"""Finish probabilities from ranker scores via Plackett-Luce simulation with DNFs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1pred import config, dnf, evaluate
from f1pred.features import FEATURES

TEMPERATURES = np.geomspace(0.1, 10, 81)
DEFAULT_TEMPERATURE = 1.0
MIN_CALIBRATION_RACES = 5


def simulate_positions(scores, temperature: float, n_sims: int = 20_000, seed: int = 0,
                       dnf_prob=None) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noisy = np.asarray(scores, float) / temperature + rng.gumbel(size=(n_sims, len(scores)))
    if dnf_prob is not None:
        retired = rng.random(noisy.shape) < np.asarray(dnf_prob, float)
        noisy = np.where(retired, -1e6 + rng.random(noisy.shape), noisy)
    return np.argsort(np.argsort(-noisy, axis=1), axis=1) + 1


def finish_probabilities(scores: pd.Series, temperature: float, n_sims: int = 20_000, seed: int = 0,
                         dnf_prob=None) -> pd.DataFrame:
    pos = simulate_positions(scores, temperature, n_sims, seed, dnf_prob)
    out = pd.DataFrame({
        "WinPct": (pos == 1).mean(axis=0) * 100,
        "PodiumPct": (pos <= 3).mean(axis=0) * 100,
        "PointsPct": (pos <= 10).mean(axis=0) * 100,
        "ExpectedPosition": pos.mean(axis=0),
    }, index=scores.index)
    if dnf_prob is not None:
        out["DnfPct"] = np.asarray(dnf_prob, float) * 100
    return out


def order_log_likelihood(scores, finish_positions, temperature: float, top_k: int | None = None) -> float:
    order = np.argsort(np.asarray(finish_positions, float), kind="stable")
    s = np.asarray(scores, float)[order] / temperature
    tail_logsumexp = np.logaddexp.accumulate(s[::-1])[::-1]
    return float((s - tail_logsumexp)[:top_k].sum())


def fit_temperature(races: list[pd.DataFrame], top_k: int | None = None, finishers_only: bool = False) -> float:
    if finishers_only:
        races = [r[r["Dnf"].ne(1)] for r in races]
    ll = [sum(order_log_likelihood(r["Score"], r["FinishPosition"], t, top_k) for r in races)
          for t in TEMPERATURES]
    return float(TEMPERATURES[int(np.argmax(ll))])


def calibrate(feats: pd.DataFrame, before_race_idx: int, features: list[str] = FEATURES,
              n_races: int = 12) -> tuple[float, int]:
    done = feats[(feats["RaceIdx"] < before_race_idx) & feats["FinishPosition"].notna()]
    indices = [i for i in sorted(done["RaceIdx"].unique()) if i >= 3][-n_races:]
    if len(indices) < MIN_CALIBRATION_RACES:
        return DEFAULT_TEMPERATURE, len(indices)
    races = list(evaluate.walk_forward(feats, indices, features))
    return fit_temperature(races, config.CALIBRATION_TOP_K, finishers_only=True), len(indices)


def rolling_probabilities(races: list[pd.DataFrame], feats: pd.DataFrame | None = None,
                          n_sims: int = 10_000) -> list[pd.DataFrame]:
    """Probabilities per race using only earlier races; pass feats to include the DNF model."""
    reliability = dnf.add_reliability_features(feats) if feats is not None else None
    out = []
    for i, race in enumerate(races):
        temperature = (fit_temperature(races[:i], config.CALIBRATION_TOP_K, finishers_only=reliability is not None)
                       if i >= MIN_CALIBRATION_RACES else DEFAULT_TEMPERATURE)
        dnf_prob = (dnf.race_dnf_probability(reliability, int(race["RaceIdx"].iloc[0]), race)
                    if reliability is not None else None)
        probs = finish_probabilities(race["Score"], temperature, n_sims, dnf_prob=dnf_prob)
        out.append(race.join(probs).assign(Temperature=temperature))
    return out


def calibration_report(scored: list[pd.DataFrame]) -> dict[str, float]:
    rows = []
    for race in scored:
        actual = race["FinishPosition"].rank(method="first")
        row = {
            "WinnerLogLoss": -np.log(max(race.loc[actual.idxmin(), "WinPct"] / 100, 1e-4)),
            "UniformWinnerLogLoss": np.log(len(race)),
            "PodiumBrier": ((race["PodiumPct"] / 100 - (actual <= 3)) ** 2).mean(),
            "PointsBrier": ((race["PointsPct"] / 100 - (actual <= 10)) ** 2).mean(),
        }
        if "DnfPct" in race:
            row["DnfBrier"] = ((race["DnfPct"] / 100 - race["Dnf"]) ** 2).mean()
        rows.append(row)
    return pd.DataFrame(rows).mean().to_dict()


def walk_forward_calibration(races: list[pd.DataFrame], feats: pd.DataFrame | None = None) -> dict[str, float]:
    return calibration_report(rolling_probabilities(races, feats))

"""Finish probabilities from ranker scores via Plackett-Luce simulation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1pred import config, evaluate
from f1pred.features import FEATURES

TEMPERATURES = np.geomspace(0.1, 10, 81)
DEFAULT_TEMPERATURE = 1.0
MIN_CALIBRATION_RACES = 5


def simulate_positions(scores, temperature: float, n_sims: int = 20_000, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noisy = np.asarray(scores, float) / temperature + rng.gumbel(size=(n_sims, len(scores)))
    return np.argsort(np.argsort(-noisy, axis=1), axis=1) + 1


def finish_probabilities(scores: pd.Series, temperature: float, n_sims: int = 20_000, seed: int = 0) -> pd.DataFrame:
    pos = simulate_positions(scores, temperature, n_sims, seed)
    return pd.DataFrame({
        "WinPct": (pos == 1).mean(axis=0) * 100,
        "PodiumPct": (pos <= 3).mean(axis=0) * 100,
        "PointsPct": (pos <= 10).mean(axis=0) * 100,
        "ExpectedPosition": pos.mean(axis=0),
    }, index=scores.index)


def order_log_likelihood(scores, finish_positions, temperature: float, top_k: int | None = None) -> float:
    order = np.argsort(np.asarray(finish_positions, float), kind="stable")
    s = np.asarray(scores, float)[order] / temperature
    tail_logsumexp = np.logaddexp.accumulate(s[::-1])[::-1]
    return float((s - tail_logsumexp)[:top_k].sum())


def fit_temperature(races: list[pd.DataFrame], top_k: int | None = None) -> float:
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
    return fit_temperature(races, config.CALIBRATION_TOP_K), len(indices)


def rolling_probabilities(races: list[pd.DataFrame], n_sims: int = 10_000) -> list[pd.DataFrame]:
    out = []
    for i, race in enumerate(races):
        temperature = (fit_temperature(races[:i], config.CALIBRATION_TOP_K)
                       if i >= MIN_CALIBRATION_RACES else DEFAULT_TEMPERATURE)
        probs = finish_probabilities(race["Score"], temperature, n_sims)
        out.append(race.join(probs).assign(Temperature=temperature))
    return out


def walk_forward_calibration(races: list[pd.DataFrame]) -> dict[str, float]:
    reports = []
    for i, race in enumerate(races):
        temperature = (fit_temperature(races[:i], config.CALIBRATION_TOP_K)
                       if i >= MIN_CALIBRATION_RACES else DEFAULT_TEMPERATURE)
        reports.append(calibration_report([race], temperature))
    return pd.DataFrame(reports).mean().to_dict()


def calibration_report(races: list[pd.DataFrame], temperature: float, n_sims: int = 5_000) -> dict[str, float]:
    winner_log_loss, podium_brier = [], []
    for race in races:
        probs = finish_probabilities(race["Score"], temperature, n_sims)
        actual = race["FinishPosition"].rank(method="first")
        winner_log_loss.append(-np.log(max(probs.loc[actual.idxmin(), "WinPct"] / 100, 1e-4)))
        podium_brier.append(((probs["PodiumPct"] / 100 - (actual <= 3)) ** 2).mean())
    return {
        "WinnerLogLoss": float(np.mean(winner_log_loss)),
        "UniformWinnerLogLoss": float(np.mean([np.log(len(r)) for r in races])),
        "PodiumBrier": float(np.mean(podium_brier)),
    }

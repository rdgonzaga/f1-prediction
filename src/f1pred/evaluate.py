"""Walk-forward backtest against the grid-order baseline."""
from __future__ import annotations

from collections.abc import Iterator

import pandas as pd

from f1pred import config
from f1pred import model as ranker
from f1pred.features import FEATURE_SETS, FEATURES

METRICS = ["Spearman", "WinnerHit", "PodiumHitRate", "MAE"]


def race_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    actual_rank = actual.rank(method="first")
    pred_rank = predicted.rank(method="first")
    top3_pred = set(pred_rank[pred_rank <= 3].index)
    top3_actual = set(actual_rank[actual_rank <= 3].index)
    return {
        "Spearman": actual_rank.corr(pred_rank, method="spearman"),
        "WinnerHit": float(pred_rank.idxmin() == actual_rank.idxmin()),
        "PodiumHitRate": len(top3_pred & top3_actual) / 3,
        "MAE": (actual_rank - pred_rank).abs().mean(),
    }


def season_race_indices(feats: pd.DataFrame, season: int, start_round: int) -> list[int]:
    done = feats[(feats["Season"] == season) & feats["FinishPosition"].notna() & (feats["RoundNumber"] >= start_round)]
    return [int(i) for i in sorted(done["RaceIdx"].unique())]


def walk_forward(feats: pd.DataFrame, race_indices: list[int], features: list[str] = FEATURES) -> Iterator[pd.DataFrame]:
    for idx in race_indices:
        race = ranker.training_rows(feats[feats["RaceIdx"] == idx])
        train = ranker.training_rows(feats[feats["RaceIdx"] < idx])
        model = ranker.fit(train, target_era=config.era_index(int(race["Season"].iloc[0])), features=features)
        yield ranker.predict_order(model, race).loc[race.index]


def backtest(feats: pd.DataFrame, season: int, start_round: int = 4,
             features: list[str] = FEATURES) -> pd.DataFrame:
    rows = []
    for pred in walk_forward(feats, season_race_indices(feats, season, start_round), features):
        base = {f"Grid{k}": v for k, v in race_metrics(pred["FinishPosition"], pred["Grid"]).items()}
        rows.append({
            "Season": season, "RoundNumber": int(pred["RoundNumber"].iloc[0]), "EventName": pred["EventName"].iloc[0],
            **race_metrics(pred["FinishPosition"], pred["PredictedPosition"]), **base,
        })
    return pd.DataFrame(rows)


def compare(feats: pd.DataFrame, season: int, start_round: int, set_names: list[str]) -> pd.DataFrame:
    table = {}
    for name in set_names:
        summary = summarize(backtest(feats, season, start_round, FEATURE_SETS[name]))
        table[name] = summary["Model"]
    table["GridBaseline"] = summary["GridBaseline"]
    return pd.DataFrame(table)


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Model": [results[m].mean() for m in METRICS],
        "GridBaseline": [results[f"Grid{m}"].mean() for m in METRICS],
    }, index=METRICS).round(3)

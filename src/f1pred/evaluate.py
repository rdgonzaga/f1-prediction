"""Walk-forward backtest against the grid-order baseline."""
from __future__ import annotations

import pandas as pd

from f1pred import config
from f1pred import model as ranker


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


def backtest(feats: pd.DataFrame, season: int, start_round: int = 4) -> pd.DataFrame:
    rows = []
    rounds = feats.loc[(feats["Season"] == season) & feats["FinishPosition"].notna(), "RoundNumber"]
    for rnd in sorted(r for r in rounds.unique() if r >= start_round):
        race = ranker.training_rows(feats[(feats["Season"] == season) & (feats["RoundNumber"] == rnd)])
        race_idx = race["RaceIdx"].iloc[0]
        train = ranker.training_rows(feats[feats["RaceIdx"] < race_idx])

        model = ranker.fit(train, target_era=config.era_index(season))
        pred = ranker.predict_order(model, race).loc[race.index]
        base = {f"Grid{k}": v for k, v in race_metrics(race["FinishPosition"], race["Grid"]).items()}
        rows.append({
            "Season": season, "RoundNumber": rnd, "EventName": race["EventName"].iloc[0],
            **race_metrics(race["FinishPosition"], pred["PredictedPosition"]), **base,
        })
    return pd.DataFrame(rows)


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    metrics = ["Spearman", "WinnerHit", "PodiumHitRate", "MAE"]
    return pd.DataFrame({
        "Model": [results[m].mean() for m in metrics],
        "GridBaseline": [results[f"Grid{m}"].mean() for m in metrics],
    }, index=metrics).round(3)

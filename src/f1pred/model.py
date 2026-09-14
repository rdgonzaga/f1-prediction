"""XGBoost ranker over driver-race rows, grouped by race."""
from __future__ import annotations

import numpy as np
import pandas as pd
from xgboost import XGBRanker

from f1pred import config
from f1pred.features import FEATURES

PARAMS = {
    "objective": "rank:pairwise",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "max_depth": 3,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "random_state": 42,
}


def training_rows(feats: pd.DataFrame) -> pd.DataFrame:
    started = feats["FinishPosition"].notna() & feats["Classified"].astype("string").ne("W")
    return feats[started].sort_values(["RaceIdx", "FinishPosition"])


def fit(train: pd.DataFrame, target_era: int | None = None,
        era_weight: float = config.CURRENT_ERA_SAMPLE_WEIGHT) -> XGBRanker:
    train = train.sort_values("RaceIdx")
    starters = train.groupby("RaceIdx")["FinishPosition"].transform("count")
    label = (starters - train["FinishPosition"]).clip(lower=0).astype(int)
    # XGBoost ranking takes one weight per race group.
    race_eras = train.drop_duplicates("RaceIdx")["Season"].map(config.era_index)
    target_era = race_eras.max() if target_era is None else target_era
    weights = np.where(race_eras.eq(target_era), era_weight, 1.0)

    model = XGBRanker(**PARAMS)
    model.fit(train[FEATURES], label, qid=train["RaceIdx"], sample_weight=weights)
    return model


def predict_order(model: XGBRanker, race: pd.DataFrame) -> pd.DataFrame:
    out = race.copy()
    out["Score"] = model.predict(out[FEATURES])
    out["PredictedPosition"] = out["Score"].rank(ascending=False, method="first").astype(int)
    return out.sort_values("PredictedPosition")

"""Per-driver DNF probability from pre-race reliability history."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from f1pred import config
from f1pred.features import RACE_KEYS, _per_race_history

DNF_FEATURES = ["DrvDnfSeason", "DrvDnfCareer", "TeamDnfSeason", "FieldDnfLast10", "Grid"]


def add_reliability_features(feats: pd.DataFrame) -> pd.DataFrame:
    started = feats.assign(Dnf=feats["Dnf"].where(feats["Classified"].astype("string").ne("W")), Field=0)
    team_race = started.groupby(RACE_KEYS + ["RaceIdx", "TeamId"])["Dnf"].mean().reset_index()
    team_hist = _per_race_history(team_race, ["Season", "TeamId"], {"TeamDnfSeason": ("Dnf", None)})
    field_race = started.groupby(RACE_KEYS + ["RaceIdx", "Field"])["Dnf"].mean().reset_index()
    field_hist = _per_race_history(field_race, ["Field"], {"FieldDnfLast10": ("Dnf", 10)})

    out = feats.drop(columns=["TeamDnfSeason", "FieldDnfLast10"], errors="ignore")
    out = out.merge(team_hist, on=RACE_KEYS + ["TeamId"], how="left")
    out = out.merge(field_hist.drop(columns="Field"), on=RACE_KEYS, how="left")
    out.index = feats.index
    return out


def _design(rows: pd.DataFrame, fallback: float) -> pd.DataFrame:
    X = rows[DNF_FEATURES].copy()
    X["FieldDnfLast10"] = X["FieldDnfLast10"].fillna(fallback)
    for col in ["DrvDnfSeason", "DrvDnfCareer", "TeamDnfSeason"]:
        X[col] = X[col].fillna(X["FieldDnfLast10"])
    return X


def fit(train: pd.DataFrame, target_era: int | None = None, era_weight: float = config.DNF_CURRENT_ERA_WEIGHT):
    rows = train[train["FinishPosition"].notna() & train["Classified"].astype("string").ne("W")]
    weights = np.where(rows["Season"].map(config.era_index) == target_era, era_weight, 1.0)
    base_rate = float(np.average(rows["Dnf"], weights=weights)) if len(rows) else 0.0
    if rows["Dnf"].nunique() < 2:
        return base_rate
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.5))
    model.fit(_design(rows, base_rate), rows["Dnf"].astype(int), logisticregression__sample_weight=weights)
    model.base_rate_ = base_rate
    return model


def predict_proba(model, race: pd.DataFrame) -> np.ndarray:
    if isinstance(model, float):
        return np.full(len(race), model)
    return model.predict_proba(_design(race, model.base_rate_))[:, 1]


def race_dnf_probability(reliability: pd.DataFrame, race_idx: int, race: pd.DataFrame) -> np.ndarray:
    season = int(reliability.loc[reliability["RaceIdx"] == race_idx, "Season"].iloc[0])
    model = fit(reliability[reliability["RaceIdx"] < race_idx], target_era=config.era_index(season))
    return predict_proba(model, reliability.loc[race.index])

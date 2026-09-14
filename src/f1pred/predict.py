"""Predict an upcoming race once qualifying is available."""
from __future__ import annotations

import fastf1
import pandas as pd

from f1pred import build, config, fetch, probabilities
from f1pred import model as ranker
from f1pred.features import build_features


def resolve_round(season: int, event: str) -> int:
    if event.isdigit():
        return int(event)
    return int(fastf1.get_event(season, event)["RoundNumber"])


def run(season: int, event: str, refresh: bool = True) -> pd.DataFrame:
    rnd = resolve_round(season, event)
    if refresh:
        fetch.run([season], rounds=[rnd])
        build.run()

    feats = build_features(*build.load_processed())
    race = feats[(feats["Season"] == season) & (feats["RoundNumber"] == rnd)]
    if race.empty or race["QPosition"].isna().all():
        raise SystemExit(f"No qualifying data for {season} round {rnd} yet.")

    train = ranker.training_rows(feats[feats["RaceIdx"] < race["RaceIdx"].iloc[0]])
    pred = ranker.predict_order(ranker.fit(train, target_era=config.era_index(season)), race)
    temperature, n_calibration = probabilities.calibrate(feats, race["RaceIdx"].iloc[0])
    pred = pred.join(probabilities.finish_probabilities(pred["Score"], temperature))

    out = pred[["PredictedPosition", "Abbreviation", "TeamName", "Grid",
                "WinPct", "PodiumPct", "PointsPct", "ExpectedPosition"]].round(1)
    out_dir = config.PROCESSED_DIR / "predictions"
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_dir / f"{season}_R{rnd:02d}.csv", index=False)
    print(f"\n{race['EventName'].iloc[0]} {season} — predicted finishing order "
          f"(probability temperature {temperature:.2f}, calibrated on {n_calibration} races)")
    print(out.to_string(index=False))
    return out

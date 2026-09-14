"""Predict an upcoming race once qualifying is available."""
from __future__ import annotations

import fastf1
import pandas as pd

from f1pred import build, config, dnf, fetch, probabilities
from f1pred import model as ranker
from f1pred.features import build_features

OUTPUT_COLS = ["PredictedPosition", "Abbreviation", "TeamName", "Grid",
               "WinPct", "PodiumPct", "PointsPct", "DnfPct", "ExpectedPosition"]


def resolve_round(season: int, event: str) -> int:
    if event.isdigit():
        return int(event)
    return int(fastf1.get_event(season, event)["RoundNumber"])


def markdown_table(df: pd.DataFrame) -> str:
    header = "| " + " | ".join(df.columns) + " |"
    divider = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, divider, *rows])


def headline(out: pd.DataFrame) -> str:
    favourite = out.iloc[0]
    podium = ", ".join(out.sort_values("PodiumPct", ascending=False)["Abbreviation"].head(3))
    return (f"Favourite: {favourite['Abbreviation']} ({favourite['WinPct']:.0f}% win) | "
            f"Most likely podium: {podium}")


def run(season: int, event: str, refresh: bool = True) -> pd.DataFrame:
    rnd = resolve_round(season, event)
    if refresh:
        fetch.run([season], rounds=[rnd])
        build.run()

    entries, laps, conditions = build.load_processed()
    feats = build_features(entries, laps, conditions)
    race = feats[(feats["Season"] == season) & (feats["RoundNumber"] == rnd)]
    if race.empty or race["QPosition"].isna().all():
        raise SystemExit(f"No qualifying data for {season} round {rnd} yet.")

    train = ranker.training_rows(feats[feats["RaceIdx"] < race["RaceIdx"].iloc[0]])
    pred = ranker.predict_order(ranker.fit(train, target_era=config.era_index(season)), race)
    race_idx = int(race["RaceIdx"].iloc[0])
    temperature, n_calibration = probabilities.calibrate(feats, race_idx)
    dnf_prob = dnf.race_dnf_probability(dnf.add_reliability_features(feats), race_idx, pred)
    pred = pred.join(probabilities.finish_probabilities(pred["Score"], temperature, dnf_prob=dnf_prob))
    out = pred[OUTPUT_COLS].round(1)

    event_name = race["EventName"].iloc[0]
    race_label = f"{season} R{rnd:02d} "
    warnings = [i.removeprefix(race_label) for i in build.data_checks(entries, conditions, laps)
                if i.startswith(race_label) and not i.endswith("no race results")]

    out_dir = config.PROCESSED_DIR / "predictions"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"{season}_R{rnd:02d}"
    out.to_csv(stem.with_suffix(".csv"), index=False)
    summary = [f"# {event_name} {season}", "", headline(out), ""]
    summary += [f"> Warning: {w}" for w in warnings] + ([""] if warnings else [])
    summary += [markdown_table(out), "",
                f"Probability temperature {temperature:.2f}, calibrated on {n_calibration} races."]
    stem.with_suffix(".md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"\n{event_name} {season} — predicted finishing order "
          f"(probability temperature {temperature:.2f}, calibrated on {n_calibration} races)")
    for w in warnings:
        print(f"Warning: {w}")
    print(headline(out))
    print(out.to_string(index=False))
    print(f"\nSaved {stem.with_suffix('.csv').name} and {stem.with_suffix('.md').name} to {out_dir}")
    return out

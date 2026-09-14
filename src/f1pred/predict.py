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


def parse_penalties(items: list[str] | None) -> dict[str, int]:
    penalties = {}
    for item in items or []:
        driver, sep, places = item.partition("=")
        if not sep or not places.isdigit():
            raise SystemExit(f"Bad penalty '{item}', expected e.g. VER=5")
        penalties[driver.upper()] = int(places)
    return penalties


def apply_grid_penalties(race: pd.DataFrame, penalties: dict[str, int], pitlane: set[str]) -> pd.Series:
    """Grid slots after place penalties; pit lane starters get 0."""
    unknown = (set(penalties) | pitlane) - set(race["Abbreviation"])
    if unknown:
        raise SystemExit(f"Unknown driver(s) {sorted(unknown)}; entries are {sorted(race['Abbreviation'])}")
    quali = race["QPosition"].fillna(race["QPosition"].max() + 1)
    ranked = race.assign(
        Target=quali + race["Abbreviation"].map(penalties).fillna(0),
        Penalised=race["Abbreviation"].isin(penalties),
        Quali=quali,
    )
    starters = ranked[~ranked["Abbreviation"].isin(pitlane)].sort_values(["Target", "Penalised", "Quali"])
    grid = pd.Series(0.0, index=race.index)
    grid.loc[starters.index] = range(1, len(starters) + 1)
    return grid


def describe_overrides(penalties: dict[str, int], pitlane: set[str]) -> str:
    parts = [f"{d} +{p}" for d, p in penalties.items()] + [f"{d} pit lane" for d in sorted(pitlane)]
    return "Grid overrides: " + ", ".join(parts) if parts else ""


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


def run(season: int, event: str, refresh: bool = True, penalties: dict[str, int] | None = None,
        pitlane: list[str] | None = None) -> pd.DataFrame:
    rnd = resolve_round(season, event)
    if refresh:
        fetch.run([season], rounds=[rnd])
        build.run()

    penalties = penalties or {}
    pitlane = {d.upper() for d in pitlane or []}
    entries, laps, conditions = build.load_processed()
    target = (entries["Season"] == season) & (entries["RoundNumber"] == rnd)
    if penalties or pitlane:
        entries.loc[target, "GridPosition"] = apply_grid_penalties(entries[target], penalties, pitlane)
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
    overrides = describe_overrides(penalties, pitlane)
    pre_race = not race["FinishPosition"].notna().any()
    out.assign(
        DriverId=pred["DriverId"],
        PreRace=pre_race,
        PredictedAtUTC=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S"),
        GridOverrides=overrides,
    ).to_csv(stem.with_suffix(".csv"), index=False)
    summary = [f"# {event_name} {season}", "", headline(out), ""]
    summary += [] if pre_race else ["_Made after the race result was known (not counted by `score`)._", ""]
    summary += [overrides, ""] if overrides else []
    summary += [f"> Warning: {w}" for w in warnings] + ([""] if warnings else [])
    summary += [markdown_table(out), "",
                f"Probability temperature {temperature:.2f}, calibrated on {n_calibration} races."]
    stem.with_suffix(".md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"\n{event_name} {season} — predicted finishing order "
          f"(probability temperature {temperature:.2f}, calibrated on {n_calibration} races)")
    for w in warnings:
        print(f"Warning: {w}")
    if overrides:
        print(overrides)
    print(headline(out))
    print(out.to_string(index=False))
    print(f"\nSaved {stem.with_suffix('.csv').name} and {stem.with_suffix('.md').name} to {out_dir}")
    return out

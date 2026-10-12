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


def apply_grid_penalties(race: pd.DataFrame, penalties: dict[str, int], pitlane: set[str],
                         slots: dict[str, int] | None = None) -> pd.Series:
    """Grid slots after place penalties and exact slots; pit lane starters get 0."""
    slots = slots or {}
    unknown = (set(penalties) | pitlane | set(slots)) - set(race["Abbreviation"])
    if unknown:
        raise SystemExit(f"Unknown driver(s) {sorted(unknown)}; entries are {sorted(race['Abbreviation'])}")
    n_starters = len(race) - len(pitlane)
    if set(slots) & pitlane:
        raise SystemExit(f"{sorted(set(slots) & pitlane)} can't have a grid slot and start from the pit lane")
    if len(set(slots.values())) < len(slots) or any(not 1 <= s <= n_starters for s in slots.values()):
        raise SystemExit(f"Grid slots must be unique and between 1 and {n_starters}: {slots}")
    quali = race["QPosition"].fillna(race["QPosition"].max() + 1)
    ranked = race.assign(
        Target=quali + race["Abbreviation"].map(penalties).fillna(0),
        Penalised=race["Abbreviation"].isin(penalties),
        Quali=quali,
    )
    fixed = race["Abbreviation"].isin(slots)
    rest = ranked[~ranked["Abbreviation"].isin(pitlane) & ~fixed].sort_values(["Target", "Penalised", "Quali"])
    grid = pd.Series(0.0, index=race.index)
    grid.loc[fixed] = race.loc[fixed, "Abbreviation"].map(slots).astype(float)
    grid.loc[rest.index] = [s for s in range(1, n_starters + 1) if s not in set(slots.values())]
    return grid


def describe_overrides(penalties: dict[str, int], pitlane: set[str], slots: dict[str, int] | None = None) -> str:
    parts = ([f"{d} +{p}" for d, p in penalties.items()] + [f"{d} P{s}" for d, s in (slots or {}).items()]
             + [f"{d} pit lane" for d in sorted(pitlane)])
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


def guard_already_run(race: pd.DataFrame, season: int, rnd: int, backfill: bool) -> bool:
    """Refuse a race that already has a result, since scoring ignores those predictions."""
    already_run = bool(race["FinishPosition"].notna().any())
    if already_run and not backfill:
        raise SystemExit(
            f"{season} round {rnd} has already been run, so a prediction saved now would not count "
            f"when scoring. Pass --backfill to save one anyway."
        )
    return already_run


def run(season: int, event: str, refresh: bool = True, penalties: dict[str, int] | None = None,
        pitlane: list[str] | None = None, backfill: bool = False,
        slots: dict[str, int] | None = None) -> pd.DataFrame:
    rnd = resolve_round(season, event)
    if refresh:
        fetch.run([season], rounds=[rnd])
        build.run()

    penalties = penalties or {}
    pitlane = {d.upper() for d in pitlane or []}
    slots = slots or {}
    entries, laps, conditions = build.load_processed()
    target = (entries["Season"] == season) & (entries["RoundNumber"] == rnd)
    if penalties or pitlane or slots:
        entries.loc[target, "GridPosition"] = apply_grid_penalties(entries[target], penalties, pitlane, slots)
    feats = build_features(entries, laps, conditions)
    race = feats[(feats["Season"] == season) & (feats["RoundNumber"] == rnd)]
    if race.empty or race["QPosition"].isna().all():
        raise SystemExit(f"No qualifying data for {season} round {rnd} yet.")
    already_run = guard_already_run(race, season, rnd, backfill)

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

    stem = config.prediction_path(season, rnd, "")
    out_dir = stem.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    overrides = describe_overrides(penalties, pitlane, slots)
    pre_race = not already_run
    out.assign(
        DriverId=pred["DriverId"],
        EventName=event_name,
        PreRace=pre_race,
        PredictedAtUTC=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S"),
        GridOverrides=overrides,
        Temperature=temperature,
        CalibrationRaces=n_calibration,
        Warnings="; ".join(warnings),
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

"""Score saved pre-race predictions against actual results."""
from __future__ import annotations

import pandas as pd

from f1pred import build, config, evaluate, fetch

PREDICTIONS_DIR = config.PROCESSED_DIR / "predictions"


def load_predictions(season: int | None = None) -> list[tuple[int, int, pd.DataFrame]]:
    out = []
    for path in sorted(PREDICTIONS_DIR.glob("*_R*.csv")):
        season_str, rnd_str = path.stem.split("_R")
        if season is None or int(season_str) == season:
            out.append((int(season_str), int(rnd_str), pd.read_csv(path)))
    return out


def score_race(pred: pd.DataFrame, actual: pd.DataFrame) -> dict[str, float] | None:
    merged = pred.merge(actual[["Abbreviation", "FinishPosition", "Classified"]], on="Abbreviation", how="inner")
    merged = merged[merged["FinishPosition"].notna() & merged["Classified"].astype("string").ne("W")]
    if merged.empty:
        return None
    actual_rank = merged["FinishPosition"].rank(method="first")
    row = evaluate.race_metrics(merged["FinishPosition"], merged["PredictedPosition"])
    row |= {f"Grid{k}": v for k, v in evaluate.race_metrics(merged["FinishPosition"], merged["Grid"]).items()}
    if "WinPct" in merged:
        row["WinnerWinPct"] = float(merged.loc[actual_rank.idxmin(), "WinPct"])
        row["PodiumBrier"] = float(((merged["PodiumPct"] / 100 - (actual_rank <= 3)) ** 2).mean())
    return row


def is_pre_race(pred: pd.DataFrame) -> bool:
    return "PreRace" in pred and bool(pred["PreRace"].all())


def run(season: int | None = None, refresh: bool = False, include_backfilled: bool = False) -> pd.DataFrame:
    predictions = load_predictions(season)
    if not predictions:
        raise SystemExit(f"No saved predictions in {PREDICTIONS_DIR}")
    if refresh:
        for s in sorted({s for s, _, _ in predictions}):
            fetch.run([s], rounds=sorted({r for s2, r, _ in predictions if s2 == s}))
        build.run()

    entries = build.load_processed()[0]
    rows, skipped = [], []
    for s, rnd, pred in predictions:
        label = f"{s} R{rnd:02d}"
        if not include_backfilled and not is_pre_race(pred):
            skipped.append(f"{label}: made after the race (use --include-backfilled)")
            continue
        actual = entries[(entries["Season"] == s) & (entries["RoundNumber"] == rnd)]
        row = score_race(pred, actual) if not actual.empty else None
        if row is None:
            skipped.append(f"{label}: no race result yet")
            continue
        rows.append({"Season": s, "RoundNumber": rnd, "EventName": actual["EventName"].iloc[0], **row})

    for line in skipped:
        print(f"Skipped {line}")
    if not rows:
        print("Nothing to score yet.")
        return pd.DataFrame()

    card = pd.DataFrame(rows)
    card.to_csv(PREDICTIONS_DIR / "scorecard.csv", index=False)
    print(card.round(3).to_string(index=False))
    print(f"\n{len(card)} race(s) scored")
    print(evaluate.summarize(card).to_string())
    if "WinnerWinPct" in card:
        print(f"\nAvg win chance given to the actual winner: {card['WinnerWinPct'].mean():.1f}%")
        print(f"Podium Brier: {card['PodiumBrier'].mean():.3f}")
    return card

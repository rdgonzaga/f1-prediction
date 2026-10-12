"""Season scorecard data and the standalone scorecard page."""
from __future__ import annotations

import pandas as pd

from f1pred import build, config, score
from f1pred.report import screenshot

PODIUM_BINS = [0, 5, 20, 50, 80, 100]


def season_data(season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-race scores and per-driver rows for every saved prediction with a full result."""
    entries = build.load_processed()[0]
    races, drivers = [], []
    for s, rnd, pred in score.load_predictions(season):
        actual = entries[(entries["Season"] == s) & (entries["RoundNumber"] == rnd)]
        merged = score.merge_actual(pred, actual)
        if merged is None:
            continue
        live = score.is_pre_race(pred)
        row = score.score_race(pred, actual)
        races.append({"RoundNumber": rnd, "EventName": actual["EventName"].iloc[0], "Live": live, **row})
        drivers.append(merged.assign(RoundNumber=rnd, Live=live,
                                     OnPodium=merged["FinishPosition"].rank(method="first") <= 3))
    if not races:
        raise SystemExit(f"No scored predictions for {season} yet.")
    return pd.DataFrame(races).sort_values("RoundNumber"), pd.concat(drivers, ignore_index=True)


def podium_calibration(drivers: pd.DataFrame) -> pd.DataFrame:
    """Predicted podium chance against how often it happened, in bands."""
    bands = pd.cut(drivers["PodiumPct"], PODIUM_BINS, include_lowest=True)
    out = drivers.groupby(bands, observed=True).agg(
        Said=("PodiumPct", "mean"), Did=("OnPodium", "mean"), N=("OnPodium", "size"))
    out["Did"] *= 100
    out.index = [f"{int(b.left)}–{int(b.right)}%" for b in out.index]
    return out


def run(season: int, png: bool = True):
    from f1pred.web import build as web
    out_path = config.PREDICTIONS_DIR / str(season) / f"{season}_season.html"
    out_path.write_text(web.standalone_scorecard(season), encoding="utf-8", newline="\n")
    print(f"Wrote {out_path}")
    png_path = screenshot(out_path) if png else None
    if png_path:
        print(f"Wrote {png_path}, ready to send as a picture.")
    return out_path

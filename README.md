# f1-prediction

Predicts the full F1 race finishing order after qualifying.

## Setup
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

## Usage
```
python -m f1pred fetch                      # 2022 → current year, newest first, resumable
python -m f1pred fetch --seasons 2026 2025  # fetch in this order
python -m f1pred build                      # combine into data/processed, run data checks
python -m f1pred backtest                   # walk-forward on latest season vs grid order
python -m f1pred backtest --features grid quali pace all --probabilities
python -m f1pred predict 2026 Singapore     # after qualifying: fetch weekend, rebuild, predict
python -m f1pred predict 2026 Singapore --penalty VER=5 --pitlane STR
python -m f1pred score --refresh            # after the race: compare saved predictions with results
pytest
```
`score` only counts predictions saved before the race result existed. `--include-backfilled` adds the others.
`predict` prints the favourite and likely podium, plus win, podium, points and DNF chances for every driver. It saves `data/processed/predictions/<season>_R<round>.csv` and a `.md` summary.
FastF1 limits API calls to 500 per hour, so a full fetch takes a few hours. Re-running skips sessions that are already done and re-fetches any saved without race control messages. Each race weekend, `fetch` only downloads the new sessions.

## Future seasons
Seasons run from 2022 to the current year automatically. When a new regulation era begins (next expected 2031), add its first year to `ERA_STARTS` in `src/f1pred/config.py`. Races from the same era as the predicted race get 3× training weight.

## Storage
Telemetry is never loaded. Car and position data were ~97% of the old cache (992 MB for 6 sessions). Each session is saved as compact parquet, and the event's FastF1 cache is deleted afterwards. The full dataset is expected to stay under ~300 MB.

## Approach
- **Data:** 2022–2026 practice, qualifying, sprint and race sessions.
- **2026 regulations:** team pecking orders reset, so features are relative and carry across eras: grid, quali gap to pole and teammate, long-run practice pace, within-season driver/team form, career driver traits, and track overtaking difficulty. Same-era races get 3× weight.
- **Model:** `XGBRanker` (pairwise), grouped by race.
- **Probabilities:** each race is simulated 20,000 times from the ranker scores (Plackett-Luce). The spread is fitted on how the top 3 finished, and a logistic DNF model sends retirements to the back.
- **Validation:** walk-forward over 2026 rounds, reported next to the grid-order baseline (Spearman, winner hit, podium hit rate, position MAE).
- **Leakage:** features only use earlier races plus the same weekend's pre-race sessions (see `tests/test_features.py`).

## Layout
```
src/f1pred/   config, fetch, build, features, model, evaluate, predict, CLI
tests/        leakage, build and metric tests
notebooks/    exploration and result review only
```

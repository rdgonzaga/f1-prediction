# Notebooks

The pipeline lives in `src/f1pred` and runs from the CLI. These notebooks only look at its output.

Install `requirements-dev.txt` and run `python -m f1pred build` first so `data/processed` is up to date.

1. `00_project_setup.ipynb`: environment and FastF1 sanity check.
2. `01_eda.ipynb`: data coverage, grid → finish patterns, and which features track the result.
3. `02_backtest_review.ipynb`: walk-forward backtest vs grid order, feature-set comparison, and probability calibration.
4. `03_next_race.ipynb`: predicted order and win/podium chances for a race after qualifying. Set `EVENT` to a round that hasn't been raced yet.

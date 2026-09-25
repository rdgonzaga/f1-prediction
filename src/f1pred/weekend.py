"""One command for a race weekend: fetch, build, predict, report."""
from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from f1pred import build, fetch, predict, report


def quali_ready(log_df: pd.DataFrame, season: int, rnd: int) -> bool:
    row = log_df[log_df["SessionKey"] == fetch.session_key(season, rnd, "Q")]
    return bool((row["Status"] == "DONE").any())


def run(season: int, event: str, penalties: dict[str, int] | None = None, pitlane: list[str] | None = None,
        wait_minutes: int = 0, poll_minutes: int = 5, sleep: Callable[[float], None] = time.sleep) -> Path:
    rnd = predict.resolve_round(season, event)
    waited = 0
    while not quali_ready(fetch.run([season], rounds=[rnd]), season, rnd):
        if waited >= wait_minutes:
            raise SystemExit(
                f"Qualifying for {season} round {rnd} isn't available yet. It usually lands about 90 minutes "
                f"after the session starts; try again later, or pass --wait 60 to keep retrying.")
        print(f"Qualifying not available yet, retrying in {poll_minutes} min...")
        sleep(poll_minutes * 60)
        waited += poll_minutes

    build.run()
    predict.run(season, str(rnd), refresh=False, penalties=penalties, pitlane=pitlane)
    return report.run(season, rnd)

"""Project paths, extraction scope and regulation eras."""
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_DIR = RAW_DIR / "fastf1_cache"
LOG_PATH = RAW_DIR / "extraction_log.csv"
# One row per team per season; add the new season's rows before its first race.
POWER_UNITS_PATH = PROJECT_ROOT / "reference" / "power_units.csv"

FIRST_SEASON = 2022

# Add the first season of each new regulation era here (e.g. 2031).
ERA_STARTS = [2022, 2026]
CURRENT_ERA_SAMPLE_WEIGHT = 3.0
# Reliability shifts with new regulations, so the DNF model leans much harder on the current era.
DNF_CURRENT_ERA_WEIGHT = 10.0

# Win/podium probability spread is fitted on the order of the first k finishers only.
CALIBRATION_TOP_K = 3

# Sprint formats vary by year, so sessions are read from each event's schedule.
SESSION_CODES = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint Shootout": "SQ",
    "Sprint Qualifying": "SQ",
    "Sprint": "S",
    "Race": "R",
}

# FastF1 renames some locations between seasons; keys are accent-stripped lowercase.
LOCATION_ALIASES = {
    "miami gardens": "miami",
    "monte carlo": "monaco",
}

# Events confirmed to have moved to a different track (not just renamed).
DIFFERENT_VENUES = {"Spanish Grand Prix"}

MAX_RETRIES = 3
RETRY_SLEEP_SECONDS = 2
# FastF1 caps all API calls at 500/hour.
RATE_LIMIT_WAIT_SECONDS = 600


def seasons() -> list[int]:
    return list(range(date.today().year, FIRST_SEASON - 1, -1))


def era_index(season: int) -> int:
    return sum(season >= start for start in ERA_STARTS) - 1

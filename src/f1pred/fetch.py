"""FastF1 extractor without telemetry, with an official results fallback; clears each event's cache after saving."""
from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone

import fastf1
import pandas as pd

from f1pred import config, official

LOG_COLUMNS = [
    "SessionKey", "Season", "RoundNumber", "EventName", "SessionCode",
    "Status", "Source", "Attempts", "ResultsRows", "LapsRows", "UpdatedAtUTC", "Error",
]


QUEUE_COLUMNS = ["SessionKey", "Season", "RoundNumber", "EventName", "EventFormat", "Country", "Location",
                 "SessionName", "SessionCode", "SessionStartUTC"]


def td_to_seconds(series: pd.Series) -> pd.Series:
    return pd.to_timedelta(series, errors="coerce").dt.total_seconds()


def session_key(season: int, round_number: int, code: str) -> str:
    return f"{season}_R{round_number:02d}_{code}"


def enable_cache() -> None:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(config.CACHE_DIR), use_requests_cache=False)
    fastf1.set_log_level("ERROR")


def build_queue(seasons: list[int], max_events: int | None = None,
                rounds: list[int] | None = None) -> pd.DataFrame:
    """One row per (event, session) that has already taken place."""
    now = pd.Timestamp.now(tz="UTC")
    rows = []
    for season in seasons:
        schedule = fastf1.get_event_schedule(season, include_testing=False)
        schedule = schedule[schedule["RoundNumber"] > 0].sort_values("RoundNumber")
        if rounds:
            schedule = schedule[schedule["RoundNumber"].isin(rounds)]
        if max_events:
            schedule = schedule.head(max_events)

        for _, event in schedule.iterrows():
            rnd = int(event["RoundNumber"])
            for i in range(1, 6):
                name = event.get(f"Session{i}")
                code = config.SESSION_CODES.get(name)
                if code is None:
                    continue
                start = pd.to_datetime(event.get(f"Session{i}DateUtc"), errors="coerce")
                if pd.isna(start) or start.tz_localize("UTC") > now:
                    continue
                rows.append({
                    "SessionKey": session_key(season, rnd, code),
                    "Season": season,
                    "RoundNumber": rnd,
                    "EventName": event["EventName"],
                    "EventFormat": event["EventFormat"],
                    "Country": event["Country"],
                    "Location": event["Location"],
                    "SessionName": name,
                    "SessionCode": code,
                    "SessionStartUTC": start,
                })
    return pd.DataFrame(rows, columns=QUEUE_COLUMNS)


def load_log() -> pd.DataFrame:
    if config.LOG_PATH.exists():
        log_df = pd.read_csv(config.LOG_PATH).drop_duplicates("SessionKey", keep="last")
        if "Source" not in log_df:
            log_df["Source"] = log_df["Status"].eq("DONE").map({True: "fastf1", False: ""})
        return log_df
    return pd.DataFrame(columns=LOG_COLUMNS)


def upsert_log(log_df: pd.DataFrame, row: dict) -> pd.DataFrame:
    log_df = log_df[log_df["SessionKey"] != row["SessionKey"]]
    log_df = pd.concat([log_df, pd.DataFrame([row])], ignore_index=True)
    log_df = log_df[LOG_COLUMNS].sort_values(["Season", "RoundNumber", "SessionCode"])
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_df.to_csv(config.LOG_PATH, index=False)
    return log_df


def sessions_missing_messages() -> set[str]:
    """Sessions saved without race control messages (Deleted flag all null)."""
    keys = set()
    for path in config.RAW_DIR.glob("*/R*_laps.parquet"):
        deleted = pd.read_parquet(path, columns=["Deleted"])["Deleted"]
        if len(deleted) and deleted.isna().all():
            rnd, code, _ = path.stem.split("_")
            keys.add(session_key(int(path.parent.name), int(rnd[1:]), code))
    return keys


def sessions_missing_results() -> set[str]:
    """Races and sprints saved before full results were out (GridPosition all null)."""
    keys = set()
    for code in ("R", "S"):
        for path in config.RAW_DIR.glob(f"*/R*_{code}_results.parquet"):
            grid = pd.read_parquet(path, columns=["GridPosition"])["GridPosition"]
            if len(grid) and grid.isna().all():
                rnd = path.stem.split("_")[0]
                keys.add(session_key(int(path.parent.name), int(rnd[1:]), code))
    return keys


def _meta(job) -> dict:
    return {
        "Season": int(job.Season),
        "RoundNumber": int(job.RoundNumber),
        "EventName": job.EventName,
        "EventFormat": job.EventFormat,
        "Location": job.Location,
        "SessionCode": job.SessionCode,
    }


def extract_official(job) -> dict[str, pd.DataFrame]:
    results = official.session_results(int(job.Season), job.SessionCode, job.Country, job.Location, job.EventName)
    for k, v in _meta(job).items():
        results[k] = v
    return {"results": results}


def extract_session(job) -> dict[str, pd.DataFrame]:
    session = fastf1.get_session(int(job.Season), int(job.RoundNumber), job.SessionName)
    session.load(laps=True, telemetry=False, weather=True, messages=True)
    meta = _meta(job)

    results = session.results.reset_index(drop=True).copy()
    for col in ["Q1", "Q2", "Q3", "Time"]:
        if col in results.columns:
            results[f"{col}Seconds"] = td_to_seconds(results[col])
            results = results.drop(columns=col)

    laps = pd.DataFrame(session.laps).reset_index(drop=True)
    for col in laps.columns:
        if pd.api.types.is_timedelta64_dtype(laps[col]):
            laps[f"{col}Seconds"] = td_to_seconds(laps[col])
            laps = laps.drop(columns=col)

    weather = session.weather_data.copy() if session.weather_data is not None else pd.DataFrame()
    if "Time" in weather.columns:
        weather["TimeSeconds"] = td_to_seconds(weather["Time"])
        weather = weather.drop(columns="Time")

    track_status = session.track_status.copy() if session.track_status is not None else pd.DataFrame()
    if "Time" in track_status.columns:
        track_status["TimeSeconds"] = td_to_seconds(track_status["Time"])
        track_status = track_status.drop(columns="Time")

    tables = {"results": results, "laps": laps, "weather": weather, "track_status": track_status}
    for df in tables.values():
        for k, v in meta.items():
            df[k] = v
    return tables


def save_tables(job, tables: dict[str, pd.DataFrame]) -> None:
    out_dir = config.RAW_DIR / str(job.Season)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        if len(df):
            df.to_parquet(out_dir / f"R{int(job.RoundNumber):02d}_{job.SessionCode}_{name}.parquet", index=False)


def purge_event_cache(season: int, event_name: str) -> None:
    season_dir = config.CACHE_DIR / str(season)
    if not season_dir.exists():
        return
    safe = event_name.replace(" ", "_")
    for folder in season_dir.glob(f"*_{safe}"):
        shutil.rmtree(folder, ignore_errors=True)


def run(seasons: list[int], max_events: int | None = None, rounds: list[int] | None = None,
        retry_errors: bool = True, keep_cache: bool = False) -> pd.DataFrame:
    enable_cache()
    queue = build_queue(seasons, max_events, rounds)
    log_df = load_log()
    done = set(log_df.loc[log_df["Status"] == "DONE", "SessionKey"])
    if not retry_errors:
        done |= set(log_df.loc[log_df["Status"] == "ERROR", "SessionKey"])
    from_official = set(log_df.loc[log_df["Source"].eq("official"), "SessionKey"])
    refetch = done & (sessions_missing_messages() | sessions_missing_results() | from_official)
    done -= refetch
    todo = queue[~queue["SessionKey"].isin(done)]
    print(f"Sessions in scope: {len(queue)} | done: {len(queue) - len(todo)} | "
          f"to fetch: {len(todo)} (incl. {len(refetch & set(queue['SessionKey']))} re-fetches)")

    for (season, rnd), event_jobs in todo.groupby(["Season", "RoundNumber"], sort=False):
        for job in event_jobs.itertuples(index=False):
            status, source, error, attempts, tables = "ERROR", "", "", 0, {}
            if job.SessionCode in official.PAGES and job.SessionKey not in from_official:
                try:
                    tables = extract_official(job)
                    save_tables(job, tables)
                    status, source, error = "DONE", "official", "formula1.com first; FastF1 fills laps later"
                except Exception as exc:
                    error = f"official: {type(exc).__name__}: {exc}"
            while status == "ERROR" and attempts < config.MAX_RETRIES:
                attempts += 1
                try:
                    tables = extract_session(job)
                    save_tables(job, tables)
                    status, source, error = "DONE", "fastf1", ""
                    break
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    if type(exc).__name__ == "RateLimitExceededError":
                        attempts -= 1
                        print(f"  rate limited, waiting {config.RATE_LIMIT_WAIT_SECONDS // 60} min...")
                        time.sleep(config.RATE_LIMIT_WAIT_SECONDS)
                    elif attempts < config.MAX_RETRIES:
                        time.sleep(config.RETRY_SLEEP_SECONDS * attempts)

            if status == "ERROR" and job.SessionCode in official.PAGES and job.SessionKey in from_official:
                try:
                    tables = extract_official(job)
                    save_tables(job, tables)
                    status, source, error = "DONE", "official", f"FastF1 failed ({error[:120]}); used formula1.com"
                except Exception as exc:
                    error = f"{error[:150]} | official: {type(exc).__name__}: {exc}"

            log_df = upsert_log(log_df, {
                "SessionKey": job.SessionKey,
                "Season": job.Season,
                "RoundNumber": job.RoundNumber,
                "EventName": job.EventName,
                "SessionCode": job.SessionCode,
                "Status": status,
                "Source": source,
                "Attempts": attempts,
                "ResultsRows": len(tables.get("results", [])),
                "LapsRows": len(tables.get("laps", [])),
                "UpdatedAtUTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "Error": error[:300],
            })
            print(f"  {job.SessionKey:<14} {job.EventName:<28} {status}"
                  + (" (official results only)" if source == "official" else "")
                  + (f"  ({error[:80]})" if error and status == "ERROR" else ""))

        if not keep_cache:
            purge_event_cache(int(season), event_jobs["EventName"].iloc[0])

    return log_df

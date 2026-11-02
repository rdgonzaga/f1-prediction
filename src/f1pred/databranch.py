"""Mirror data/ to an orphan `data` branch so a CI run starts from the same files as this PC."""
from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from f1pred import config

BRANCH = "data"
REMOTE_REF = f"origin/{BRANCH}"
PATHS = ["data/raw", "data/processed/predictions"]
EXCLUDE = ":(exclude)data/raw/fastf1_cache"
CHUNK = 100


def git(*args: str, index: Path | None = None) -> str:
    env = {**os.environ, "GIT_INDEX_FILE": str(index)} if index else None
    return subprocess.run(["git", *args], cwd=config.PROJECT_ROOT, env=env, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def _tip(run_git: Callable[..., str]) -> str | None:
    try:
        run_git("fetch", "origin", f"+refs/heads/{BRANCH}:refs/remotes/{REMOTE_REF}")
    except subprocess.CalledProcessError:
        return None
    return run_git("rev-parse", REMOTE_REF)


def push(message: str, run_git: Callable[..., str] = git) -> bool:
    """Commit data/ onto the branch if it changed. A rejected push is left for the next run."""
    tip = _tip(run_git)
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "index"
        run_git("add", "-f", "--", *PATHS, EXCLUDE, index=index)
        tree = run_git("write-tree", index=index)
    if tip and tree == run_git("rev-parse", f"{tip}^{{tree}}"):
        return False
    parent = ("-p", tip) if tip else ()
    commit = run_git("commit-tree", tree, *parent, "-m", message)
    try:
        run_git("push", "origin", f"{commit}:refs/heads/{BRANCH}")
    except subprocess.CalledProcessError:
        print("Data branch moved while pushing; the next run will push data/ again.")
        return False
    print("Pushed data/ to the data branch.")
    return True


def pull(run_git: Callable[..., str] = git) -> list[str]:
    """Copy in files the branch has and this copy doesn't. Never overwrites, so local edits are safe."""
    tip = _tip(run_git)
    if not tip:
        return []
    listed = run_git("ls-tree", "-r", "--name-only", tip).splitlines()
    missing = [f for f in listed if f and not (config.PROJECT_ROOT / f).exists()]
    if not missing:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "index"
        run_git("read-tree", tip, index=index)
        for i in range(0, len(missing), CHUNK):
            run_git("checkout-index", "-f", "--", *missing[i:i + CHUNK], index=index)
    print(f"Copied {len(missing)} file(s) from the data branch.")
    return missing

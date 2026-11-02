import subprocess

from f1pred import databranch


def fake_git(tip="aaa", tip_tree="t1", tree="t1", files="", push_fails=False):
    calls = []

    def run_git(*args, index=None):
        calls.append((args, index is not None))
        if args[:2] == ("fetch", "origin"):
            if tip is None:
                raise subprocess.CalledProcessError(128, "git fetch")
            return ""
        if args[0] == "rev-parse":
            return tip_tree if args[-1].endswith("^{tree}") else tip
        if args[0] == "write-tree":
            return tree
        if args[0] == "commit-tree":
            return "new"
        if args[0] == "ls-tree":
            return files
        if args[0] == "push" and push_fails:
            raise subprocess.CalledProcessError(1, "git push")
        return ""
    return run_git, calls


def names(calls):
    return [c[0][0] for c in calls]


def test_push_skips_when_data_is_unchanged():
    run_git, calls = fake_git()
    assert not databranch.push("x", run_git)
    assert "commit-tree" not in names(calls) and "push" not in names(calls)


def test_push_commits_on_top_of_the_branch():
    run_git, calls = fake_git(tree="t2")
    assert databranch.push("chore: update data", run_git)
    assert (("commit-tree", "t2", "-p", "aaa", "-m", "chore: update data"), False) in calls
    assert calls[-1] == (("push", "origin", "new:refs/heads/data"), False)


def test_push_snapshots_data_in_a_separate_index():
    run_git, calls = fake_git(tree="t2")
    databranch.push("x", run_git)
    add = next(c for c in calls if c[0][0] == "add")
    assert add[1] and set(databranch.PATHS) <= set(add[0])
    assert any(a.startswith(":(exclude)") and "fastf1_cache" in a for a in add[0])


def test_push_starts_the_branch_when_there_is_none():
    run_git, calls = fake_git(tip=None, tree="t2")
    assert databranch.push("x", run_git)
    assert (("commit-tree", "t2", "-m", "x"), False) in calls


def test_rejected_push_is_skipped():
    run_git, _ = fake_git(tree="t2", push_fails=True)
    assert not databranch.push("x", run_git)


def test_pull_only_adds_files_missing_here(tmp_path, monkeypatch):
    monkeypatch.setattr(databranch.config, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data/raw").mkdir(parents=True)
    (tmp_path / "data/raw/mine.csv").write_text("local")
    run_git, calls = fake_git(files="data/raw/mine.csv\ndata/raw/new.parquet\n")
    assert databranch.pull(run_git) == ["data/raw/new.parquet"]
    assert (("read-tree", "aaa"), True) in calls
    assert calls[-1] == (("checkout-index", "-f", "--", "data/raw/new.parquet"), True)


def test_pull_does_nothing_without_a_branch_or_new_files(tmp_path, monkeypatch):
    monkeypatch.setattr(databranch.config, "PROJECT_ROOT", tmp_path)
    run_git, calls = fake_git(tip=None)
    assert databranch.pull(run_git) == []
    run_git, calls = fake_git(files="")
    assert databranch.pull(run_git) == []
    assert "checkout-index" not in names(calls)

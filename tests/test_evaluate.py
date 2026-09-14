import pandas as pd
import pytest

from f1pred import evaluate
from f1pred.features import build_features
from test_features import make_data


def test_perfect_prediction_metrics():
    actual = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    m = evaluate.race_metrics(actual, actual)
    assert m == pytest.approx({"Spearman": 1.0, "WinnerHit": 1.0, "PodiumHitRate": 1.0, "MAE": 0.0})


def test_backtest_runs_on_synthetic_data():
    feats = build_features(*make_data())
    results = evaluate.backtest(feats, season=2026, start_round=2)
    assert list(results["RoundNumber"]) == [2, 3, 4]
    summary = evaluate.summarize(results)
    assert set(summary.columns) == {"Model", "GridBaseline"}
    assert results["Spearman"].between(-1, 1).all()


def test_compare_feature_sets():
    feats = build_features(*make_data())
    table = evaluate.compare(feats, season=2026, start_round=3, set_names=["grid", "all"])
    assert list(table.columns) == ["grid", "all", "GridBaseline"]
    assert list(table.index) == ["Spearman", "WinnerHit", "PodiumHitRate", "MAE"]

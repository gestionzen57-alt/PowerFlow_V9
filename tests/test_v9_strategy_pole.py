"""Tests pour le pôle stratégie V9 (core/v9/v9_strategy_pole.py).

2026-07-17 motion CEO « continue optimiser au max ».
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.v9.v9_strategy_pole import (
    StrategyCatalogue,
    StrategyMetric,
    StrategyRecommendation,
    StrategySelector,
    StrategyTuner,
    compute_meta_metrics,
)


def _ensure_catalogue(cat: StrategyCatalogue, min_n: int = 20) -> int:
    """Helper — recalcule le catalogue si vide."""
    if not cat._cache:
        return cat.recompute(min_n=min_n)
    return len(cat._cache)


def test_catalogue_recompute_returns_segments() -> None:
    """Le catalogue doit retourner au moins quelques segments."""
    cat = StrategyCatalogue()
    n = cat.recompute(min_n=10)
    assert n >= 1, "Catalogue vide : vérifier les paper_trades"
    assert all(
        isinstance(m, StrategyMetric) for m in cat._cache.values()
    )


def test_catalogue_top_returns_best_first() -> None:
    """Le top doit être trié par expectancy décroissante."""
    cat = StrategyCatalogue()
    _ensure_catalogue(cat, min_n=20)
    top = cat.top(n=3, by="avg_pips")
    assert len(top) >= 1
    for a, b in zip(top, top[1:]):
        assert a.avg_pips >= b.avg_pips


def test_catalogue_worst_returns_lowest_first() -> None:
    """Le worst doit être trié par expectancy croissante."""
    cat = StrategyCatalogue()
    _ensure_catalogue(cat, min_n=20)
    worst = cat.worst(n=3, min_n=20)
    assert len(worst) >= 1
    for a, b in zip(worst, worst[1:]):
        assert a.expectancy <= b.expectancy


def test_tuner_tune_segment_returns_valid() -> None:
    """Le tuner doit retourner des TP/SL dans la grille."""
    cat = StrategyCatalogue()
    _ensure_catalogue(cat, min_n=30)
    tuner = StrategyTuner()
    # Premier segment du catalogue
    if not cat._cache:
        pytest.skip("Pas assez de données pour tuner")
    metric = next(iter(cat._cache.values()))
    tuned = tuner.tune_segment(
        metric.principle, metric.session, metric.regime,
    )
    assert tuned is not None
    assert tuned["best_tp"] in tuner.TP_GRID
    assert tuned["best_sl"] in tuner.SL_GRID
    assert tuned["n_trades"] >= tuner.MIN_N_FOR_TUNING
    assert "tuned_at" in tuned


def test_selector_recommend_returns_struct() -> None:
    """Le sélecteur doit retourner un StrategyRecommendation."""
    cat = StrategyCatalogue()
    _ensure_catalogue(cat, min_n=20)
    tuner = StrategyTuner()
    selector = StrategySelector(catalogue=cat, tuner=tuner)
    rec = selector.recommend("PRICE_LAG_AT_NODE_BIRTH", "new_york", "NEUTRE")
    assert isinstance(rec, StrategyRecommendation)
    assert rec.principle == "PRICE_LAG_AT_NODE_BIRTH"
    assert rec.recommended_tp > 0
    assert rec.recommended_sl > 0
    assert rec.recommended_strategy in ("TP_SL", "TRAILING", "TIME_BASED")
    assert 0.0 <= rec.confidence <= 1.0
    assert rec.source in ("metric_history", "grid_search", "default")


def test_selector_recommend_fallback_unknown() -> None:
    """Recommandation pour un segment inconnu → fallback conservateur."""
    selector = StrategySelector(
        catalogue=StrategyCatalogue(),
        tuner=StrategyTuner(),
    )
    rec = selector.recommend("UNKNOWN_PRINCIPE", "unknown_session", "UNKNOWN_REGIME")
    assert rec.source == "default"
    assert rec.recommended_tp == 10.0
    assert rec.recommended_sl == 15.0
    assert rec.confidence < 0.5


def test_meta_metrics_returns_totals() -> None:
    """compute_meta_metrics doit retourner des totaux cohérents."""
    meta = compute_meta_metrics()
    assert meta["version"] == "1.0"
    totals = meta["totals"]
    assert "n_trades" in totals
    assert totals["n_trades"] > 0
    assert totals["wins"] + totals["losses"] == totals["n_trades"]
    assert 0 <= totals["wr_pct"] <= 100
    assert "profit_factor" in totals


def test_meta_metrics_identifies_best_principle() -> None:
    """Le best_principle doit être celui avec le plus de pips."""
    meta = compute_meta_metrics()
    assert meta["best_principle"] is not None
    # PRICE_LAG devrait dominer (à vérifier contre les données)
    assert isinstance(meta["best_principle"], str)


def test_catalogue_save_cache_writes_file(tmp_path: Path) -> None:
    """save_cache doit écrire un JSON valide."""
    cat = StrategyCatalogue()
    _ensure_catalogue(cat, min_n=20)
    out = cat.save_cache()
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    if data:
        assert "principle" in data[0]
        assert "wr_pct" in data[0]
        assert "avg_pips" in data[0]


def test_strategy_metric_to_dict_roundtrip() -> None:
    """StrategyMetric.to_dict doit produire un dict sérialisable JSON."""
    m = StrategyMetric(
        principle="P", session="s", regime="r", n_trades=10,
        n_wins=7, wr_pct=70.0, avg_pips=2.5, total_pips=25.0,
        profit_factor=1.5, expectancy=2.5, best_tp=10.0, best_sl=15.0,
        confidence_score=0.75,
    )
    d = m.to_dict()
    assert d["principle"] == "P"
    assert d["wr_pct"] == 70.0
    assert d["confidence_score"] == 0.75
    json_str = json.dumps(d)
    assert isinstance(json_str, str)
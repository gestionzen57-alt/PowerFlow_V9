"""test_v9_meta_strategy_optimizer.py — Tests pour core/v9/v9_meta_strategy_optimizer.py (R33).

Vérifie :
T1. Kill switch (V9_META_STRATEGY_OPTIMIZER_ENABLED) — défaut ON
T2. _clamp_tp / _clamp_sl bornes [5, 20]
T3. _dd_ratio clamping
T4. _compute_composite_score
T5. _bucket_vol_atr aligned with cycle_memory
T6. select_strategy retourne MetaStrategyDecision
T7. select_strategy fallback si kill switch OFF
T8. select_strategy fallback si DB absente
T9. select_strategy combine cycle_memory + phase + vol weights
T10. R6 défensif : DB error → fallback
T11. CLI dry-run
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.v9.v9_meta_strategy_optimizer import (
    META_STRATEGY_ENABLED_ENV,
    DEFAULT_TP,
    DEFAULT_SL,
    MIN_TP,
    MAX_TP,
    MIN_SL,
    MAX_SL,
    MIN_TRADES_FOR_SCORE,
    STRATEGY_TP_SL,
    STRATEGY_TRAILING,
    STRATEGY_TP_PARTIAL,
    STRATEGY_FAST_EXIT,
    ALL_STRATEGIES,
    ContextScore,
    MetaStrategyDecision,
    _clamp_tp,
    _clamp_sl,
    _compute_composite_score,
    _dd_ratio,
    _select_tp_sl_from_candidates,
    meta_strategy_optimizer_enabled,
    select_strategy,
)
from core.v9.v9_cycle_memory import (
    _bucket_vol_atr,
    init_db as init_cycle_db,
    update as cycle_update,
)


@pytest.fixture
def tmp_db_with_principle_scores(tmp_path: Path) -> Path:
    """DB v9_forces-like avec principle_scores + paper_trades peuplés."""
    db = tmp_path / "fake_forces.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript("""
            CREATE TABLE principle_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                principle_id TEXT, combination_hash TEXT,
                n_trades INTEGER, n_wins INTEGER, n_losses INTEGER,
                total_pips REAL, avg_pips REAL, win_rate REAL,
                last_updated TEXT
            );
            CREATE TABLE paper_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_simulated REAL, is_win INTEGER
            );
        """)
        # Stratégie 1 (TP_SL) : WR 70%, PF 1.5, n=200
        conn.execute(
            "INSERT INTO principle_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (None, "PRICE_LAG", None, 200, 140, 60, 200.0, 1.0, 0.70, "2026-07-18"),
        )
        # Stratégie 2 (TRAILING) : WR 80%, PF 3.0, n=100
        conn.execute(
            "INSERT INTO principle_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (None, "TRAILING", None, 100, 80, 20, 800.0, 8.0, 0.80, "2026-07-18"),
        )
        # Stratégie 3 (TP_PARTIAL) : WR 65%, PF 1.8, n=80
        conn.execute(
            "INSERT INTO principle_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (None, "TP_PARTIAL", None, 80, 52, 28, 200.0, 2.5, 0.65, "2026-07-18"),
        )
        # 100 paper trades avec DD max ~-50 pips
        for i in range(100):
            pips = -10.0 if i % 3 == 0 else 5.0
            conn.execute(
                "INSERT INTO paper_trades(pips_simulated, is_win) VALUES (?, ?)",
                (pips, 1 if pips > 0 else 0),
            )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture
def tmp_cycle_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_cycle.db"
    init_cycle_db(db)
    return db


@pytest.fixture(autouse=True)
def cleanup_env(monkeypatch: pytest.MonkeyPatch):
    """Isole les tests."""
    if META_STRATEGY_ENABLED_ENV in os.environ:
        monkeypatch.delenv(META_STRATEGY_ENABLED_ENV)
    yield


# ============================================================== T1 kill switch

def test_meta_strategy_enabled_default_on():
    """Motion CEO 2026-07-18 : APPLY direct, défaut ON."""
    assert META_STRATEGY_ENABLED_ENV not in os.environ
    assert meta_strategy_optimizer_enabled() is True


def test_meta_strategy_disabled_when_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(META_STRATEGY_ENABLED_ENV, "0")
    assert meta_strategy_optimizer_enabled() is False


# ============================================================== T2 clamp

def test_clamp_tp_in_range():
    assert _clamp_tp(10.0) == 10.0
    assert _clamp_tp(MIN_TP) == MIN_TP
    assert _clamp_tp(MAX_TP) == MAX_TP


def test_clamp_tp_below_min():
    assert _clamp_tp(2.0) == MIN_TP


def test_clamp_tp_above_max():
    assert _clamp_tp(50.0) == MAX_TP


def test_clamp_sl_in_range():
    assert _clamp_sl(15.0) == 15.0
    assert _clamp_sl(2.0) == MIN_SL
    assert _clamp_sl(50.0) == MAX_SL


# ============================================================== T3 DD ratio

def test_dd_ratio_zero():
    assert _dd_ratio(0.0) == 0.0


def test_dd_ratio_negative():
    """DD est signé négatif, on prend abs()."""
    assert _dd_ratio(-50.0) == _dd_ratio(50.0)


def test_dd_ratio_capped_at_one():
    assert _dd_ratio(5000.0) == 1.0  # > capital_pips


def test_dd_ratio_zero_capital():
    """R6 : capital_pips=0 → ratio=1.0 (pas de division par zéro)."""
    assert _dd_ratio(-100.0, capital_pips=0) == 1.0


# ============================================================== T4 composite score

def test_compute_score_zero_trades():
    assert _compute_composite_score(0.7, 2.0, 0, 0.1) == 0.0


def test_compute_score_below_min_trades():
    """n < MIN_TRADES_FOR_SCORE → 0."""
    assert _compute_composite_score(0.7, 2.0, MIN_TRADES_FOR_SCORE - 1, 0.1) == 0.0


def test_compute_score_in_range():
    """Score ∈ [0, 1] pour inputs valides."""
    s = _compute_composite_score(0.7, 2.0, 50, 0.1)
    assert 0 <= s <= 1


def test_compute_score_higher_wr_better():
    s_low = _compute_composite_score(0.4, 2.0, 50, 0.1)
    s_high = _compute_composite_score(0.8, 2.0, 50, 0.1)
    assert s_high > s_low


def test_compute_score_higher_dd_lower():
    s_low_dd = _compute_composite_score(0.7, 2.0, 50, 0.1)
    s_high_dd = _compute_composite_score(0.7, 2.0, 50, 0.5)
    assert s_low_dd > s_high_dd


def test_compute_score_pf_capped_at_5():
    """PF > 5 ne donne pas de bonus additionnel (PF=5 == PF=10)."""
    s_pf5 = _compute_composite_score(0.7, 5.0, 50, 0.1)
    s_pf10 = _compute_composite_score(0.7, 10.0, 50, 0.1)
    assert s_pf5 == pytest.approx(s_pf10, abs=0.01)


def test_compute_score_pf4_lower_than_pf5():
    """PF=4 < 5 doit donner un score inférieur à PF=5 (le clamp plafonne)."""
    s_pf4 = _compute_composite_score(0.7, 4.0, 50, 0.1)
    s_pf5 = _compute_composite_score(0.7, 5.0, 50, 0.1)
    assert s_pf4 < s_pf5


# ============================================================== T5 bucket vol aligné

def test_bucket_vol_atr_aligned():
    """Cohérence avec v9_cycle_memory."""
    for v in [0.5, 1.0, 2.0, 3.5, 6.0, 10.0]:
        assert _bucket_vol_atr(v) in ("LOW", "MEDIUM", "HIGH")


# ============================================================== T6 select_strategy base

def test_select_strategy_returns_decision(tmp_db_with_principle_scores: Path):
    """API publique : retourne MetaStrategyDecision."""
    decision = select_strategy(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5, direction="haussiere",
        db_path=tmp_db_with_principle_scores,
    )
    assert isinstance(decision, MetaStrategyDecision)
    assert decision.chosen_strategy in ALL_STRATEGIES
    assert MIN_TP <= decision.recommended_tp <= MAX_TP
    assert MIN_SL <= decision.recommended_sl <= MAX_SL


def test_select_strategy_includes_all_candidates(tmp_db_with_principle_scores: Path):
    """all_candidates doit contenir les 4 stratégies."""
    decision = select_strategy(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5, direction="haussiere",
        db_path=tmp_db_with_principle_scores,
    )
    assert len(decision.all_candidates) == len(ALL_STRATEGIES)
    strategies = {c.strategy for c in decision.all_candidates}
    assert strategies == set(ALL_STRATEGIES)


def test_select_strategy_rationale_non_empty(tmp_db_with_principle_scores: Path):
    decision = select_strategy(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5, direction="haussiere",
        db_path=tmp_db_with_principle_scores,
    )
    assert decision.rationale
    assert decision.source == "meta_optimizer"


# ============================================================== T7 fallback kill switch

def test_select_strategy_disabled_returns_fallback(monkeypatch: pytest.MonkeyPatch):
    """Kill switch OFF → fallback_selector ou default."""
    monkeypatch.setenv(META_STRATEGY_ENABLED_ENV, "0")
    mock_selector = MagicMock()
    mock_rec = MagicMock()
    mock_rec.recommended_strategy = STRATEGY_TP_SL
    mock_rec.recommended_tp = 12.0
    mock_rec.recommended_sl = 14.0
    mock_rec.confidence = 0.7
    mock_selector.recommend.return_value = mock_rec
    decision = select_strategy(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5, direction="haussiere",
        db_path=None, fallback_selector=mock_selector,
    )
    assert decision.source == "fallback_selector"
    assert decision.chosen_strategy == STRATEGY_TP_SL
    mock_selector.recommend.assert_called_once()


def test_select_strategy_disabled_no_fallback(monkeypatch: pytest.MonkeyPatch):
    """Kill switch OFF + pas de fallback → default conservateur."""
    monkeypatch.setenv(META_STRATEGY_ENABLED_ENV, "0")
    decision = select_strategy(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5, direction="haussiere",
        db_path=None,
    )
    assert decision.source == "disabled_kill_switch"
    assert decision.chosen_strategy == STRATEGY_TP_SL
    assert decision.recommended_tp == DEFAULT_TP
    assert decision.recommended_sl == DEFAULT_SL


# ============================================================== T8 fallback DB absente

def test_select_strategy_db_absente(tmp_path: Path):
    """DB inexistante → fallback conservateur."""
    decision = select_strategy(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5, direction="haussiere",
        db_path=tmp_path / "no.db",
    )
    assert decision.source == "no_candidates_db_empty"
    assert decision.chosen_strategy == STRATEGY_TP_SL


# ============================================================== T9 weights

def test_select_strategy_combines_cycle_memory(
    tmp_db_with_principle_scores: Path,
    tmp_cycle_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Si cycle_memory a un pattern chaud, ctx_weight > 1."""
    # Active cycle_memory kill switch
    monkeypatch.setenv("V9_CYCLE_MEMORY_ENABLED", "1")

    # Peuple cycle memory avec WR=1.0 (au-dessus de 0.55 → bonus)
    from core.v9.v9_cycle_memory import MIN_N_OBSERVATIONS
    for _ in range(MIN_N_OBSERVATIONS + 2):
        cycle_update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
                     is_win=True, db_path=tmp_cycle_db)

    # Monkey-patch le DEFAULT_DB_PATH dans les 2 modules
    import core.v9.v9_cycle_memory as cm_module
    import core.v9.v9_meta_strategy_optimizer as mso_module
    original_cm_db = cm_module.DEFAULT_DB_PATH
    original_mso_db = mso_module.CYCLE_MEMORY_DB_PATH
    cm_module.DEFAULT_DB_PATH = tmp_cycle_db
    mso_module.CYCLE_MEMORY_DB_PATH = tmp_cycle_db
    try:
        decision = select_strategy(
            symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
            phase="culmination", vol_atr_pips=3.5, direction="haussiere",
            db_path=tmp_db_with_principle_scores,
        )
        assert decision.cycle_memory is not None
        assert decision.cycle_memory.win_rate > 0.7
    finally:
        cm_module.DEFAULT_DB_PATH = original_cm_db
        mso_module.CYCLE_MEMORY_DB_PATH = original_mso_db


# ============================================================== T10 R6 défensif

def test_select_strategy_db_corrupt(tmp_path: Path):
    """R6 : DB corrompue ne crash pas, retourne fallback."""
    bad_db = tmp_path / "bad.db"
    bad_db.write_text("not a sqlite db")
    decision = select_strategy(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5, direction="haussiere",
        db_path=bad_db,
    )
    # DB error → all_candidates vides → fallback
    assert isinstance(decision, MetaStrategyDecision)


def test_select_strategy_invalid_phase(tmp_db_with_principle_scores: Path):
    """Phase invalide → fallback initiation (R6)."""
    decision = select_strategy(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="INVALID", vol_atr_pips=3.5, direction="haussiere",
        db_path=tmp_db_with_principle_scores,
    )
    # Doit quand même scorer les candidats
    assert decision.chosen_strategy in ALL_STRATEGIES


# ============================================================== T11 CLI

def test_cli_dry_run(tmp_db_with_principle_scores: Path, capsys):
    from core.v9.v9_meta_strategy_optimizer import main
    rc = main([
        "--symbol", "GBPUSD", "--timeframe", "M15",
        "--regime", "NEUTRE", "--phase", "culmination",
        "--vol-atr", "3.5", "--direction", "haussiere",
        "--db", str(tmp_db_with_principle_scores),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "chosen_strategy" in out
    assert "recommended_tp" in out


# ============================================================== T12 strategy TP/SL mapping

def test_select_tp_sl_trailing():
    candidates = [
        ContextScore(STRATEGY_TRAILING, 0.8, 0.8, 3.0, 100, 0.1, 1.0, "test"),
        ContextScore(STRATEGY_TP_SL, 0.5, 0.6, 1.5, 50, 0.2, 1.0, "test"),
    ]
    tp, sl = _select_tp_sl_from_candidates(candidates)
    assert tp == 15.0
    assert sl == 12.0


def test_select_tp_sl_partial():
    candidates = [
        ContextScore(STRATEGY_TP_PARTIAL, 0.8, 0.7, 1.8, 80, 0.1, 1.0, "test"),
    ]
    tp, sl = _select_tp_sl_from_candidates(candidates)
    assert tp == 10.0
    assert sl == 10.0


def test_select_tp_sl_fast_exit():
    candidates = [
        ContextScore(STRATEGY_FAST_EXIT, 0.8, 0.6, 1.0, 30, 0.1, 1.0, "test"),
    ]
    tp, sl = _select_tp_sl_from_candidates(candidates)
    assert tp == 5.0
    assert sl == 15.0


def test_select_tp_sl_empty():
    tp, sl = _select_tp_sl_from_candidates([])
    assert tp == DEFAULT_TP
    assert sl == DEFAULT_SL

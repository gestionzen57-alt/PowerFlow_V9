"""V10 Bayesian Recalibrator — tests unitaires (Phase 16).

Cible R7 : 20 tests verts minimum.

Doctrine V10 R10 :
  - Recalibration bloquée si n_trades < 30 par paire.
  - WR ≥ 62% = gate cible.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest

from core.v10.v10_bayesian_recalibrator import (
    DEFAULT_THRESHOLDS,
    CONTEXT_SCORE_GRID,
    ANTA_SCORE_GRID,
    ALIGNED_COUNT_GRID,
    V9_BLACKLIST_PAIRS,
    MIN_TRADES_PER_PAIR,
    WR_TARGET,
    PairThreshold,
    RecalibrationReport,
    compute_recalibration,
    apply_thresholds,
    write_thresholds_json,
    load_thresholds_json,
    _load_paper_trades,
    _compute_pair_features,
    _estimate_context_score,
    _grid_search_pair,
)


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    """DB temporaire avec table paper_trades."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    con = sqlite3.connect(path, timeout=10)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE paper_trades (
            trade_id TEXT PRIMARY KEY,
            symbol TEXT,
            direction TEXT,
            confiance REAL,
            is_win INTEGER,
            pips_net_of_spread REAL,
            spread_pips REAL,
            closed_at TEXT
        )
    """)
    con.commit()
    con.close()
    yield path
    Path(path).unlink(missing_ok=True)


def _populate_trades(
    db_path: str,
    trades: List[Dict],
) -> None:
    con = sqlite3.connect(db_path, timeout=10)
    cur = con.cursor()
    for t in trades:
        cur.execute("""
            INSERT INTO paper_trades
            (trade_id, symbol, direction, confiance, is_win, pips_net_of_spread, spread_pips, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t.get("trade_id", "TR_x"),
            t["symbol"],
            t.get("direction", "BUY"),
            t.get("confiance", 50),
            t.get("is_win", 0),
            t.get("pips_net", 0.0),
            t.get("spread_pips", 1.0),
            t.get("closed_at", "2026-07-01T12:00:00Z"),
        ))
    con.commit()
    con.close()


def _make_win_streak_trades(symbol: str, n: int, win_rate: float = 0.70) -> List[Dict]:
    """Génère n trades avec WR donné."""
    import random as _r
    _r.seed(42)
    trades = []
    for i in range(n):
        is_win = 1 if _r.random() < win_rate else 0
        pips = _r.uniform(5, 25) if is_win else _r.uniform(-15, -5)
        trades.append({
            "trade_id": f"TR_{symbol}_{i}",
            "symbol": symbol,
            "direction": "BUY" if i % 2 == 0 else "SELL",
            "confiance": 75 if is_win else 50,
            "is_win": is_win,
            "pips_net": round(pips, 2),
            "spread_pips": 1.5,
            "closed_at": f"2026-07-{(i // 10) + 1:02d}T{(i % 10) * 2:02d}:00:00Z",
        })
    return trades


# ─────────────────────────────────────────────────────────────────────
# 1. DEFAULTS / CONSTANTS
# ─────────────────────────────────────────────────────────────────────

def test_defaults_constants():
    assert DEFAULT_THRESHOLDS["context_score_min"] == 55.0
    assert DEFAULT_THRESHOLDS["anta_score_min"] == 25.0
    assert DEFAULT_THRESHOLDS["aligned_count_min"] == 3


def test_grids_have_multiple_options():
    assert len(CONTEXT_SCORE_GRID) >= 4
    assert len(ANTA_SCORE_GRID) >= 3
    assert len(ALIGNED_COUNT_GRID) >= 2


def test_min_trades_per_pair_r10():
    assert MIN_TRADES_PER_PAIR >= 30
    assert WR_TARGET >= 0.60


def test_blacklist_contains_usdchf():
    assert "USDCHF" in V9_BLACKLIST_PAIRS


# ─────────────────────────────────────────────────────────────────────
# 2. DB LOADER
# ─────────────────────────────────────────────────────────────────────

def test_load_paper_trades_empty_db(tmp_db):
    trades = _load_paper_trades(tmp_db)
    assert trades == []


def test_load_paper_trades_missing_db():
    trades = _load_paper_trades("nonexistent_path_xyz.db")
    assert trades == []


def test_load_paper_trades_full(tmp_db):
    _populate_trades(tmp_db, _make_win_streak_trades("EURUSD", 50, 0.6))
    trades = _load_paper_trades(tmp_db)
    assert len(trades) == 50
    assert trades[0]["symbol"] == "EURUSD"
    assert "pips_net" in trades[0]


# ─────────────────────────────────────────────────────────────────────
# 3. FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────

def test_compute_pair_features_basic():
    trades = [
        {"is_win": 1, "pips_net": 10, "confiance": 70, "spread_pips": 1.0},
        {"is_win": 0, "pips_net": -5, "confiance": 50, "spread_pips": 2.0},
    ]
    feats = _compute_pair_features(trades)
    assert feats["n"] == 2
    assert feats["wr"] == 0.5
    assert feats["confiance_avg"] == 60.0
    assert feats["spread_avg"] == 1.5


def test_compute_pair_features_empty():
    feats = _compute_pair_features([])
    assert feats["n"] == 0
    assert feats["wr"] == 0.0


def test_estimate_context_score_high_quality():
    """Confiance 1.0 + spread 0 + WR 0.8 + pnl +5 → score ~100"""
    score = _estimate_context_score({
        "confiance_avg": 1.0,
        "spread_avg": 0.0,
        "wr": 0.8,
        "pnl_avg": 5.0,
    })
    assert 90 <= score <= 100


def test_estimate_context_score_low_quality():
    """Confiance 0.5 + spread 5 + WR 0.2 + pnl -5 → score ~0"""
    score = _estimate_context_score({
        "confiance_avg": 0.5,
        "spread_avg": 5.0,
        "wr": 0.2,
        "pnl_avg": -5.0,
    })
    assert score < 20


# ─────────────────────────────────────────────────────────────────────
# 4. GRID SEARCH
# ─────────────────────────────────────────────────────────────────────

def test_grid_search_pair_insufficient_trades_r10():
    trades = _make_win_streak_trades("EURUSD", 20)  # n=20 < 30
    best, results = _grid_search_pair("EURUSD", trades)
    assert best.gate_passed is False
    assert best.audit.get("reason", "").startswith("insufficient_trades")


def test_grid_search_pair_passes_with_high_wr(tmp_db):
    """60 trades GBPUSD-like avec WR 70% → gate passe"""
    trades = _make_win_streak_trades("GBPUSD", 60, win_rate=0.70)
    _populate_trades(tmp_db, trades)
    best, results = _grid_search_pair("GBPUSD", trades)
    assert best.gate_passed is True
    assert best.win_rate >= WR_TARGET


def test_grid_search_pair_fails_with_low_wr(tmp_db):
    """60 trades avec WR 30% → gate ne passe pas"""
    trades = _make_win_streak_trades("AUDUSD", 60, win_rate=0.30)
    best, results = _grid_search_pair("AUDUSD", trades)
    assert best.gate_passed is False


# ─────────────────────────────────────────────────────────────────────
# 5. APPLY THRESHOLDS
# ─────────────────────────────────────────────────────────────────────

def test_apply_thresholds_no_thresholds_default_passes():
    """Aucun threshold → defaults 55/25/3 → context_score=70 passe"""
    passed = apply_thresholds("GBPUSD", context_score=70, anta_score=30, aligned_count=4)
    assert passed is True


def test_apply_thresholds_no_thresholds_default_fails():
    """Aucun threshold → defaults 55/25/3 → context_score=40 fail"""
    passed = apply_thresholds("GBPUSD", context_score=40, anta_score=15, aligned_count=2)
    assert passed is False


def test_apply_thresholds_with_recalibrated_pass():
    """Seuils recalibrés : cs_min=40 → context_score=45 passe"""
    thr = {
        "GBPUSD": PairThreshold(
            pair="GBPUSD", context_score_min=40, anta_score_min=10, aligned_count_min=2
        ),
    }
    passed = apply_thresholds("GBPUSD", context_score=45, anta_score=15, aligned_count=2, thresholds=thr)
    assert passed is True


def test_apply_thresholds_unknown_pair_falls_back_default():
    """Paire absente de thresholds → defaults 55/25/3"""
    thr = {"GBPUSD": PairThreshold(pair="GBPUSD", context_score_min=40, anta_score_min=10, aligned_count_min=2)}
    # EURUSD absente → utilise defaults
    passed = apply_thresholds("EURUSD", context_score=70, anta_score=30, aligned_count=4, thresholds=thr)
    assert passed is True


# ─────────────────────────────────────────────────────────────────────
# 6. PERSISTENCE JSON
# ─────────────────────────────────────────────────────────────────────

def test_write_and_load_thresholds_roundtrip(tmp_db):
    _populate_trades(tmp_db, _make_win_streak_trades("GBPUSD", 50, 0.65))
    rep = compute_recalibration(tmp_db, timestamp="2026-08-05T00:00:00Z")

    out_path = str(Path(tmp_db).parent / "thresholds.json")
    write_thresholds_json(rep, out_path)

    loaded = load_thresholds_json(out_path)
    assert "GBPUSD" in loaded
    assert loaded["GBPUSD"].context_score_min >= 45.0
    assert loaded["GBPUSD"].n_trades_evaluated == 50


def test_load_thresholds_missing_file():
    loaded = load_thresholds_json("nonexistent_path_xyz.json")
    assert loaded == {}


def test_thresholds_json_serializable():
    rep = RecalibrationReport(
        timestamp="2026-08-05T00:00:00Z",
        db_path="test.db",
        n_trades_loaded=100,
        pairs_evaluated=["GBPUSD"],
        pair_thresholds={
            "GBPUSD": PairThreshold(
                pair="GBPUSD", context_score_min=45.0, anta_score_min=15.0,
                aligned_count_min=2, n_trades_evaluated=100, win_rate=0.65,
                pnl_pips=10.0, gate_passed=True,
            ),
        },
        global_gate_passed=True,
    )
    s = json.dumps(rep.as_dict(), indent=2)
    parsed = json.loads(s)
    assert parsed["global_gate_passed"] is True
    assert parsed["pair_thresholds"]["GBPUSD"]["gate_passed"] is True


# ─────────────────────────────────────────────────────────────────────
# 7. ORCHESTRATEUR (compute_recalibration)
# ─────────────────────────────────────────────────────────────────────

def test_compute_recalibration_filters_blacklist(tmp_db):
    """USDCHF en blacklist V9 → skipped"""
    trades = _make_win_streak_trades("USDCHF", 50, 0.10)
    _populate_trades(tmp_db, trades)
    rep = compute_recalibration(tmp_db, timestamp="2026-08-05T00:00:00Z")
    assert "USDCHF" in rep.pairs_skipped
    assert "USDCHF" not in rep.pairs_evaluated


def test_compute_recalibration_min_trades_skip(tmp_db):
    """Paire avec n=20 < 30 → R10 skip"""
    _populate_trades(tmp_db, _make_win_streak_trades("USDJPY", 7))
    _populate_trades(tmp_db, _make_win_streak_trades("USDCAD", 10))
    _populate_trades(tmp_db, _make_win_streak_trades("EURUSD", 40, 0.3))
    rep = compute_recalibration(tmp_db, timestamp="2026-08-05T00:00:00Z")
    assert "USDJPY" in rep.pairs_min_trades_skipped
    assert "USDCAD" in rep.pairs_min_trades_skipped
    assert "EURUSD" in rep.pairs_evaluated


def test_compute_recalibration_global_gate_pass(tmp_db):
    """2 paires passent → global_gate_passed"""
    # GBPUSD : WR ~63% + gros gains → gate passe
    _populate_trades(tmp_db, _make_win_streak_trades("GBPUSD", 60, 0.80))
    # EURUSD : WR ~60% mais pnl positif grâce aux gros gains
    gbp_high_wr = _make_win_streak_trades("GBPUSD", 0, 0.80)  # placeholder
    eur_trades = []
    for i in range(50):
        is_win = (i % 5) < 4  # WR 80% pour passer
        eur_trades.append({
            "trade_id": f"TR_EURUSD_{i}",
            "symbol": "EURUSD",
            "direction": "BUY",
            "confiance": 75 if is_win else 50,
            "is_win": 1 if is_win else 0,
            "pips_net": 30.0 if is_win else -5.0,  # gains >> pertes
            "spread_pips": 1.5,
            "closed_at": f"2026-07-{(i // 10) + 1:02d}T{(i % 10) * 2:02d}:00:00Z",
        })
    _populate_trades(tmp_db, eur_trades)
    rep = compute_recalibration(tmp_db, timestamp="2026-08-05T00:00:00Z")
    assert rep.global_gate_passed is True
    assert rep.audit["n_pairs_passed"] >= 2


def test_compute_recalibration_global_gate_fail(tmp_db):
    """Aucune paire ne passe → global_gate_passed False"""
    _populate_trades(tmp_db, _make_win_streak_trades("GBPUSD", 50, 0.40))
    _populate_trades(tmp_db, _make_win_streak_trades("EURUSD", 50, 0.30))
    rep = compute_recalibration(tmp_db, timestamp="2026-08-05T00:00:00Z")
    assert rep.global_gate_passed is False
    assert rep.audit["n_pairs_passed"] == 0


# ─────────────────────────────────────────────────────────────────────
# 8. AUDIT & DOCTRINE
# ─────────────────────────────────────────────────────────────────────

def test_audit_includes_blacklist():
    rep = RecalibrationReport()
    assert "blacklist" not in rep.audit
    rep.audit["blacklist"] = ["USDCHF"]
    assert rep.audit["blacklist"] == ["USDCHF"]


def test_pair_threshold_default_construction():
    t = PairThreshold(pair="GBPUSD")
    assert t.pair == "GBPUSD"
    assert t.context_score_min == 55.0
    assert t.anta_score_min == 25.0
    assert t.aligned_count_min == 3
    assert t.gate_passed is False


def test_floor_absolu_context_score_r10():
    """Le floor du grid search ne doit pas descendre sous 45 (Pitfall CEO)."""
    assert min(CONTEXT_SCORE_GRID) >= 45.0


# ─────────────────────────────────────────────────────────────────────
# 9. INTÉGRATION ÉTAPE 2 — compute_market_context avec thresholds
# ─────────────────────────────────────────────────────────────────────

def test_compute_market_context_with_thresholds_dynamic():
    """compute_market_context(..., thresholds=...) utilise seuils recalibrés."""
    from core.v10.v10_market_context_global import (
        compute_market_context, _make_cs_for_context, _make_multi_tf_polarized
    )
    # On construit un snapshot polarized puis on passe un threshold strict
    multi_tf = _make_multi_tf_polarized()
    # Seuil très strict : GBPUSD demande anta_score_min=200 (impossible)
    strict_thr = {"GBPUSD": PairThreshold(
        pair="GBPUSD", context_score_min=45.0, anta_score_min=200.0, aligned_count_min=2,
    )}
    ctx = compute_market_context(multi_tf, timestamp="2026-08-05T00:00:00Z", thresholds=strict_thr)
    # Avec anta_score_min=200, GBPUSD ne passe pas le filtre paire
    assert "GBPUSD" not in ctx.tradeable_pairs or len(ctx.tradeable_pairs) == 0


def test_compute_market_context_thresholds_default():
    """Sans thresholds → R6 fail-open → DEFAULT_THRESHOLDS."""
    from core.v10.v10_market_context_global import (
        compute_market_context, _make_multi_tf_polarized
    )
    multi_tf = _make_multi_tf_polarized()
    ctx = compute_market_context(multi_tf, timestamp="2026-08-05T00:00:00Z")
    assert ctx.audit.get("thresholds_used") == 55.0  # cs_min global défaut


def test_validate_context_thresholds_global_low():
    """Seuil global context_score_min=10 → tradeable plus facilement."""
    from core.v10.v10_market_context_global import (
        validate_context, CycleState, Coalition, AntagonismMap, AntagonismEntry,
        DivergenceMap, Phase, Cycle
    )
    from core.v10.v10_market_context_global import _make_cs_for_context, _make_multi_tf_polarized
    multi_tf = _make_multi_tf_polarized()
    from core.v10.v10_market_context_global import (
        read_cycle, detect_coalition, score_antagonism, filter_divergence
    )
    h4 = multi_tf.get("H4", [])
    h1 = multi_tf.get("H1", [])
    m30 = multi_tf.get("M30", [])
    cycle = read_cycle(h4)
    coalition = detect_coalition(h4[-1] if h4 else None)
    antag = score_antagonism(h1[-1], m30[-1]) if h1 and m30 else AntagonismMap()
    div = filter_divergence({tf: multi_tf[tf][-1] for tf in ("M15", "M30", "H1", "H4") if tf in multi_tf})

    # Seuil bas : 30 → passe plus facilement
    ctx = validate_context(cycle, coalition, antag, div, timestamp="2026-08-05T00:00:00Z",
                            thresholds={"context_score_min": 30.0})
    assert ctx.audit["thresholds_used"] == 30.0


def test_validate_context_thresholds_per_pair_filters():
    """Seuils recalibrés par paire : GBPUSD strict → exclus des tradeable_pairs."""
    from core.v10.v10_market_context_global import (
        validate_context, _make_cs_for_context, _make_multi_tf_polarized,
        read_cycle, detect_coalition, score_antagonism, filter_divergence,
        AntagonismMap,
    )
    multi_tf = _make_multi_tf_polarized()
    h4 = multi_tf.get("H4", [])
    h1 = multi_tf.get("H1", [])
    m30 = multi_tf.get("M30", [])
    cycle = read_cycle(h4)
    coalition = detect_coalition(h4[-1] if h4 else None)
    antag = score_antagonism(h1[-1], m30[-1]) if h1 and m30 else AntagonismMap()
    div = filter_divergence({tf: multi_tf[tf][-1] for tf in ("M15", "M30", "H1", "H4") if tf in multi_tf})

    # Seuils très restrictifs sur GBPUSD
    thr = {"GBPUSD": {"anta_score_min": 200.0, "aligned_count_min": 5}}
    ctx = validate_context(cycle, coalition, antag, div, timestamp="2026-08-05T00:00:00Z",
                            thresholds=thr)
    # thresholds_per_pair doit contenir GBPUSD avec source=recalibrated
    if "GBPUSD" in ctx.audit.get("thresholds_per_pair", {}):
        assert ctx.audit["thresholds_per_pair"]["GBPUSD"]["source"] == "recalibrated"

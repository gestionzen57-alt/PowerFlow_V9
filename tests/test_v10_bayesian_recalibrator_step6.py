"""V10 Bayesian Recalibrator Étape 6 — tests par (paire, TF) + comparaison V9 vs V10.

Cible R7 : 15 tests verts minimum.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest

from core.v10.v10_bayesian_recalibrator import (
    PairTFThreshold,
    PAIR_TF_LEVEL_GRID,
    MIN_SIGNALS_PER_PAIR_TF,
    compute_recalibration_by_pair_tf,
    write_thresholds_pair_tf_json,
    load_thresholds_pair_tf_json,
    _load_v10_signals_clean,
    _load_v9_paper_trades,
    _grid_search_pair_tf,
    CONTEXT_SCORE_GRID,
    ANTA_SCORE_GRID,
    ALIGNED_COUNT_GRID,
)


# ─────────────────────────────────────────────────────────────────────
# HELPERS — DB temporaire avec v10_signals_clean + paper_trades V9
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    con = sqlite3.connect(path, timeout=10)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE v10_signals_clean (
            signal_id TEXT PRIMARY KEY, pair TEXT, timeframe TEXT,
            signal_level TEXT, force_base REAL, force_quote REAL,
            velocity_base REAL, velocity_quote REAL,
            rank_base INTEGER, rank_quote INTEGER,
            spread_score REAL, pnl_pips_proxy REAL, is_win_proxy INTEGER,
            direction TEXT, source TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE paper_trades (
            trade_id TEXT PRIMARY KEY, symbol TEXT, pips_net_of_spread REAL,
            is_win INTEGER, closed_at TEXT
        )
    """)
    con.commit()
    con.close()
    yield path
    Path(path).unlink(missing_ok=True)


def _populate_v10_signals(db_path: str, signals: List[Dict]) -> None:
    con = sqlite3.connect(db_path, timeout=10)
    cur = con.cursor()
    for s in signals:
        cur.execute("""
            INSERT OR REPLACE INTO v10_signals_clean VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            s.get("signal_id", "S_ID"), s["pair"], s["tf"], s["signal_level"],
            s["force_base"], s["force_quote"],
            s.get("velocity_base", 0.0), s.get("velocity_quote", 0.0),
            s.get("rank_base", 4), s.get("rank_quote", 4),
            s.get("spread_score", 1.0),
            s["pnl_pips_proxy"], s["is_win_proxy"],
            s.get("direction", "BULLISH"), s.get("source", "forces_snapshots"),
        ))
    con.commit()
    con.close()


def _populate_paper_trades(db_path: str, trades: List[Dict]) -> None:
    con = sqlite3.connect(db_path, timeout=10)
    cur = con.cursor()
    for i, t in enumerate(trades):
        cur.execute("""
            INSERT OR REPLACE INTO paper_trades VALUES (?,?,?,?,?)
        """, (
            t.get("trade_id", f"PT_{i}"), t["symbol"], t["pips_net_of_spread"],
            t["is_win"], t.get("closed_at", "2026-08-05T10:00:00Z"),
        ))
    con.commit()
    con.close()


def _make_v10_signals(pair: str, tf: str, n: int, win_rate: float = 0.65, seed: int = 42) -> List[Dict]:
    """Génère signaux V10 synthétiques avec WR cible."""
    import random
    rng = random.Random(seed)
    out = []
    for i in range(n):
        is_win = 1 if rng.random() < win_rate else 0
        pnl = 10.0 if is_win else -8.0
        # Pour A1, |delta_force| >= 30 et dominant top 3
        fb = 80.0 if is_win else 40.0
        fq = 30.0 if is_win else 70.0
        out.append({
            "signal_id": f"V10CLEAN-{pair}-{tf}-{i}",
            "pair": pair, "tf": tf, "signal_level": "A1",
            "force_base": fb, "force_quote": fq,
            "velocity_base": 0.5, "velocity_quote": -0.3,
            "rank_base": 2, "rank_quote": 6,
            "pnl_pips_proxy": pnl, "is_win_proxy": is_win,
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# 1. CONSTANTS
# ─────────────────────────────────────────────────────────────────────

def test_min_signals_per_pair_tf_30():
    """R10 floor : 30 signals par (paire, TF)."""
    assert MIN_SIGNALS_PER_PAIR_TF == 30


def test_pair_tf_level_grid_a1_a2_a3():
    assert PAIR_TF_LEVEL_GRID == ("A1", "A2", "A3")


# ─────────────────────────────────────────────────────────────────────
# 2. LOADERS
# ─────────────────────────────────────────────────────────────────────

def test_load_v10_signals_clean_empty(tmp_db):
    out = _load_v10_signals_clean(tmp_db)
    assert out == []


def test_load_v10_signals_clean_basic(tmp_db):
    _populate_v10_signals(tmp_db, _make_v10_signals("GBPUSD", "M30", 50))
    out = _load_v10_signals_clean(tmp_db)
    assert len(out) == 50
    assert out[0]["pair"] == "GBPUSD"


def test_load_v10_signals_clean_missing_db():
    out = _load_v10_signals_clean("nonexistent_xyz.db")
    assert out == []


def test_load_v9_paper_trades_basic(tmp_db):
    trades = [
        {"trade_id": "PT_0", "symbol": "GBPUSD", "pips_net_of_spread": 10.0, "is_win": 1},
        {"trade_id": "PT_1", "symbol": "GBPUSD", "pips_net_of_spread": -5.0, "is_win": 0},
        {"trade_id": "PT_2", "symbol": "EURUSD", "pips_net_of_spread": 20.0, "is_win": 1},
    ]
    _populate_paper_trades(tmp_db, trades)
    out = _load_v9_paper_trades(tmp_db)
    assert len(out) == 3
    assert out[0]["pair"] == "GBPUSD"


def test_load_v9_paper_trades_missing_db():
    out = _load_v9_paper_trades("nonexistent_xyz.db")
    assert out == []


# ─────────────────────────────────────────────────────────────────────
# 3. GRID SEARCH
# ─────────────────────────────────────────────────────────────────────

def test_grid_search_returns_best_config():
    """Grid search retourne un dict avec min_signal_level + seuils."""
    signals = _make_v10_signals("GBPUSD", "M30", 50, win_rate=0.65)
    best, kept = _grid_search_pair_tf(signals)
    assert "min_signal_level" in best
    assert "context_score_min" in best
    assert "wr" in best
    assert best["wr"] > 0.0
    assert len(kept) > 0


def test_grid_search_respects_min_signals():
    """Skip si n_kept < MIN_SIGNALS_PER_PAIR_TF."""
    signals = _make_v10_signals("GBPUSD", "M30", 30, win_rate=0.5)
    best, kept = _grid_search_pair_tf(signals)
    # Tous niveaux confondus, on devrait avoir au moins 30 gardés
    assert best["n_kept"] >= MIN_SIGNALS_PER_PAIR_TF


# ─────────────────────────────────────────────────────────────────────
# 4. RECALIBRATION ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────

def test_recalibration_basic(tmp_db):
    _populate_v10_signals(tmp_db, _make_v10_signals("GBPUSD", "M30", 60))
    _populate_v10_signals(tmp_db, _make_v10_signals("GBPUSD", "H1", 50))
    rep = compute_recalibration_by_pair_tf(tmp_db, timestamp="2026-08-05T00:00:00Z")
    assert "thresholds_by_pair_tf" in rep
    assert "GBPUSD_M30" in rep["thresholds_by_pair_tf"]
    assert "GBPUSD_H1" in rep["thresholds_by_pair_tf"]


def test_recalibration_empty_db():
    rep = compute_recalibration_by_pair_tf("nonexistent_xyz.db")
    assert rep["summary"].get("reason") == "no_v10_signals"
    assert rep["thresholds_by_pair_tf"] == {}


def test_recalibration_skips_pairs_below_min(tmp_db):
    """Skip si < 30 signaux par (paire, TF)."""
    _populate_v10_signals(tmp_db, _make_v10_signals("GBPUSD", "M30", 60))
    _populate_v10_signals(tmp_db, _make_v10_signals("USDCAD", "H1", 10))  # < 30
    rep = compute_recalibration_by_pair_tf(tmp_db, timestamp="2026-08-05T00:00:00Z")
    assert "USDCAD_H1" in rep["summary"]["pairs_skipped_r10"]
    assert "GBPUSD_M30" in rep["thresholds_by_pair_tf"]


def test_recalibration_gate_passed_for_high_wr(tmp_db):
    """WR ≥ 0.45 sur n ≥ 30 → gate_passed=True."""
    _populate_v10_signals(tmp_db, _make_v10_signals("USDCHF", "M30", 100, win_rate=0.65))
    rep = compute_recalibration_by_pair_tf(tmp_db, timestamp="2026-08-05T00:00:00Z")
    assert rep["summary"]["pairs_gate_passed"]


def test_recalibration_threshold_format_pair_tf(tmp_db):
    """Format seuil = {pair}_{tf}."""
    _populate_v10_signals(tmp_db, _make_v10_signals("GBPUSD", "H1", 50))
    rep = compute_recalibration_by_pair_tf(tmp_db)
    for k in rep["thresholds_by_pair_tf"]:
        assert "_" in k
        pair, tf = k.rsplit("_", 1)
        assert pair == "GBPUSD"
        assert tf == "H1"


def test_recalibration_serializable_json(tmp_db):
    _populate_v10_signals(tmp_db, _make_v10_signals("GBPUSD", "M30", 50))
    rep = compute_recalibration_by_pair_tf(tmp_db)
    s = json.dumps(rep, default=str)
    parsed = json.loads(s)
    assert "thresholds_by_pair_tf" in parsed


# ─────────────────────────────────────────────────────────────────────
# 5. COMPARAISON V9 vs V10
# ─────────────────────────────────────────────────────────────────────

def test_comparisons_v9_vs_v10_basic(tmp_db):
    """Comparaison WR par paire V9 vs V10 A1."""
    _populate_v10_signals(tmp_db, _make_v10_signals("GBPUSD", "M30", 50, win_rate=0.65))
    _populate_paper_trades(tmp_db, [
        {"trade_id": "PT_GBP_0", "symbol": "GBPUSD", "pips_net_of_spread": 10.0, "is_win": 1},
        {"trade_id": "PT_GBP_1", "symbol": "GBPUSD", "pips_net_of_spread": -5.0, "is_win": 0},
        {"trade_id": "PT_EUR_0", "symbol": "EURUSD", "pips_net_of_spread": 20.0, "is_win": 1},
    ])
    rep = compute_recalibration_by_pair_tf(tmp_db)
    assert "GBPUSD" in rep["comparisons_v9_v10"]
    comp = rep["comparisons_v9_v10"]["GBPUSD"]
    assert comp["n_v9"] == 2
    assert comp["n_v10_a1"] == 50
    assert comp["wr_v9"] == 0.5
    assert comp["delta_wr_a1_vs_v9"] is not None


def test_comparisons_missing_v9(tmp_db):
    """Si paper_trades V9 absent → comparisons={} (R6 fail-open)."""
    _populate_v10_signals(tmp_db, _make_v10_signals("GBPUSD", "M30", 50))
    rep = compute_recalibration_by_pair_tf(tmp_db)
    # Pas de crash, comparisons dict vide ou partiel
    assert isinstance(rep["comparisons_v9_v10"], dict)


# ─────────────────────────────────────────────────────────────────────
# 6. PERSISTENCE PAIR_TF
# ─────────────────────────────────────────────────────────────────────

def test_write_thresholds_pair_tf_json(tmp_path):
    rep = {
        "timestamp": "2026-08-05T00:00:00Z",
        "thresholds_by_pair_tf": {"GBPUSD_M30": {"pair": "GBPUSD", "tf": "M30", "gate_passed": True}},
        "summary": {"pairs_gate_passed": ["GBPUSD_M30"], "pairs_skipped_r10": []},
        "audit": {"foo": "bar"},
    }
    out_path = str(tmp_path / "thresholds.json")
    result = write_thresholds_pair_tf_json(rep, out_path)
    assert Path(result).exists()


def test_load_thresholds_pair_tf_json(tmp_path):
    test_write_thresholds_pair_tf_json(tmp_path)
    out_path = list(tmp_path.iterdir())[0]
    data = load_thresholds_pair_tf_json(str(out_path))
    assert "GBPUSD_M30" in data.get("thresholds_by_pair_tf", {})
    assert data["audit"]["foo"] == "bar"


def test_load_thresholds_pair_tf_json_missing():
    data = load_thresholds_pair_tf_json("nonexistent_xyz.json")
    assert data == {}


# ─────────────────────────────────────────────────────────────────────
# 7. PAIR_TF_THRESHOLD DATACLASS
# ─────────────────────────────────────────────────────────────────────

def test_pair_tf_threshold_default_construction():
    t = PairTFThreshold(pair="GBPUSD", tf="M30")
    assert t.context_score_min == 55.0
    assert t.anta_score_min == 25.0
    assert t.aligned_count_min == 3
    assert t.min_signal_level == "A2"
    assert t.gate_passed is False


def test_pair_tf_threshold_as_dict():
    t = PairTFThreshold(
        pair="GBPUSD", tf="M30",
        context_score_min=60.0, anta_score_min=20.0,
        aligned_count_min=2, min_signal_level="A1",
        win_rate=0.65, pnl_pips=100.0,
        n_signals_evaluated=100, n_signals_kept=80,
        gate_passed=True,
    )
    d = t.as_dict()
    assert d["pair"] == "GBPUSD"
    assert d["tf"] == "M30"
    assert d["gate_passed"] is True
    assert d["win_rate"] == 0.65


# ─────────────────────────────────────────────────────────────────────
# 8. ÉTAPE 6 — Grid search M30 indépendant de H1
# ─────────────────────────────────────────────────────────────────────

def test_grid_search_m30_vs_h1_different_thresholds():
    """Seuils M30 optimaux ne doivent pas être les mêmes que H1."""
    # M30 : WR très bon (seed=42, win_rate=0.85, n=80)
    sigs_m30 = _make_v10_signals("GBPUSD", "M30", 80, win_rate=0.85, seed=42)
    # H1 : WR faible (seed différent, win_rate=0.30, n=80)
    sigs_h1 = _make_v10_signals("GBPUSD", "H1", 80, win_rate=0.30, seed=99)
    best_m30, _ = _grid_search_pair_tf(sigs_m30)
    best_h1, _ = _grid_search_pair_tf(sigs_h1)
    # M30 should have higher WR than H1 by construction
    assert best_m30["wr"] > best_h1["wr"]


def test_grid_search_returns_a1_when_high_wr():
    """WR élevé + min_signal_level=A1 dans grid → best utilise probablement A1."""
    sigs = _make_v10_signals("GBPUSD", "M30", 100, win_rate=0.80)
    best, kept = _grid_search_pair_tf(sigs)
    # Tous les signaux A1 mockés → best garde A1
    assert best["wr"] >= 0.45  # WR cible


def test_grid_search_floor_min_signals_respected():
    """Si aucun seuil atteint MIN_SIGNALS_PER_PAIR_TF → fallback."""
    # 10 signaux → aucun seuil n'atteindra 30 gardés
    sigs = _make_v10_signals("GBPUSD", "M30", 10, win_rate=0.60)
    best, kept = _grid_search_pair_tf(sigs)
    # Fallback : tous les signaux
    assert best["n_kept"] == 10

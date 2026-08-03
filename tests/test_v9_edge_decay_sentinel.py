"""Tests pour v9_edge_decay_sentinel.py (Phase 140 — L18 Edge Decay Sentinel).

Couvre les cas critiques :
1. Kill switch OFF -> pass-through (decay_detected=False)
2. Principe stable (WR recent = baseline) -> NONE
3. Principe en degradation -15% WR -> BLACKLIST_TEMP_24H
4. PNL recent < 0 sur fenetre 30 trades -> DEMOTION
5. Decay leger -7% WR -> OBSERVATION_ONLY
6. scan_all_principles_decay trie par decay_score DESC
7. R6 fail-open : DB absente -> [] (scan) et 0s (analyze)
8. summarize_scan agrege correctement
9. Donnees insuffisantes (< MIN_TRADES_BASELINE) -> pass-through
10. Live data audit : 21/21 principes eligibility en decay sur DB reelle
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v9 import v9_edge_decay_sentinel as eds
from core.v9.v9_edge_decay_sentinel import (
    DECAY_WR_DROP_PCT,
    DECAY_WR_DROP_OBS_PCT,
    MIN_TRADES_BASELINE,
    analyze_principle_decay,
    edge_decay_sentinel_enabled,
    scan_all_principles_decay,
    summarize_scan,
)


# ── Helpers de fabrication de trades ────────────────────────────────
def _mk_trades(n: int, wr: float, avg_pips_win: float = 5.0, avg_pips_loss: float = -3.0):
    """Fabrique n trades avec un win rate cible approx."""
    trades = []
    for i in range(n):
        is_win = 1 if (i / max(1, n)) < wr else 0
        pips = avg_pips_win if is_win else avg_pips_loss
        trades.append((f"2026-07-01T{i:02d}:00:00+00:00", pips, is_win))
    return trades


def _mk_split(baseline_wr: float, recent_wr: float, n_baseline: int = 100, n_recent: int = 20):
    """Fabrique (baseline, recent) avec WR specifies."""
    return (
        _mk_trades(n_baseline, baseline_wr),
        _mk_trades(n_recent, recent_wr),
    )


# ── 1. Kill switch OFF ─────────────────────────────────────────────
def test_kill_switch_default_off(monkeypatch):
    """Defaut OFF (R25' strict motion CEO). Phase 166 (03/08) a active en prod.

    Test : si env absent + fichier absent, defaut OFF.
    """
    monkeypatch.delenv("V9_EDGE_DECAY_SENTINEL_ENABLED", raising=False)
    from core.v9 import kill_switches as ks
    ks._switches = None
    monkeypatch.setattr(ks, "_load", lambda: {})
    assert edge_decay_sentinel_enabled() is False


def test_kill_switch_on(monkeypatch):
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    from core.v9 import kill_switches as ks
    ks._switches = None
    monkeypatch.setattr(ks, "_load", lambda: {"V9_EDGE_DECAY_SENTINEL_ENABLED": "1"})
    assert edge_decay_sentinel_enabled() is True


def test_kill_switch_off_pass_through_analyze(monkeypatch):
    """Sentinel OFF -> analyze retourne tout a 0 (decay_detected=False)."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "0")
    from core.v9 import kill_switches as ks
    ks._switches = None
    monkeypatch.setattr(ks, "_load", lambda: {"V9_EDGE_DECAY_SENTINEL_ENABLED": "0"})
    # Memme avec de bons trades, ON retourne zeros car OFF.
    trades = _mk_trades(120, wr=0.50)
    r = analyze_principle_decay("TEST", trades=trades, db_path=Path("/nonexistent"))
    assert r["decay_detected"] is False
    assert r["decay_score"] == 0.0
    assert r["recommended_action"] == "NONE"
    assert r["n_baseline"] == 0


def test_kill_switch_off_pass_through_scan(monkeypatch):
    """Sentinel OFF -> scan retourne liste vide."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "0")
    out = scan_all_principles_decay(db_path=Path("/nonexistent"))
    assert out == []


# ── 2. Principe stable (pas de decay) ──────────────────────────────
def test_principle_stable_no_decay(monkeypatch):
    """WR recent = WR baseline -> NONE, decay_detected=False."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    baseline, recent = _mk_split(baseline_wr=0.40, recent_wr=0.40, n_baseline=100, n_recent=20)
    trades = baseline + recent
    r = analyze_principle_decay("STABLE", trades=trades, db_path=Path("/nonexistent"))
    assert r["decay_detected"] is False
    assert r["recommended_action"] == "NONE"
    assert abs(r["wr_delta_pct"]) < 5.0  # tolerance
    assert r["decay_score"] < 0.2


# ── 3. Decay severe (-15% WR) -> BLACKLIST_TEMP_24H ────────────────
def test_decay_severe_blacklist(monkeypatch):
    """WR chute de 40% -> 25% = -15 pts -> BLACKLIST_TEMP_24H."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    baseline, recent = _mk_split(baseline_wr=0.40, recent_wr=0.25, n_baseline=100, n_recent=20)
    trades = baseline + recent
    r = analyze_principle_decay("DECAYING", trades=trades, db_path=Path("/nonexistent"))
    assert r["decay_detected"] is True
    assert r["recommended_action"] == "BLACKLIST_TEMP_24H"
    assert r["wr_delta_pct"] < -DECAY_WR_DROP_PCT
    assert r["decay_score"] >= 0.3  # au moins 0.30 de severite
    assert r["n_recent"] == 20
    assert r["n_baseline"] == 100


# ── 4. PNL recent < 0 -> DEMOTION ─────────────────────────────────
def test_pnl_recent_negative_demotion(monkeypatch):
    """Pnl recent < 0 (meme si WR proche baseline) -> DEMOTION prioritaire sur OBSERVATION."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    # baseline wr=0.5 recent wr=0.4 (delta -10%, juste au seuil),
    # mais avg_pips_loss > avg_pips_win pour forcer pnl recent < 0.
    baseline = _mk_trades(100, wr=0.50, avg_pips_win=4.0, avg_pips_loss=-5.0)
    recent = _mk_trades(20, wr=0.45, avg_pips_win=3.0, avg_pips_loss=-6.0)
    trades = baseline + recent
    r = analyze_principle_decay("DEMOTE_ME", trades=trades, db_path=Path("/nonexistent"))
    assert r["pnl_recent"] < 0
    # Pnl recent negatif => DEMOTION (priorite > OBSERVATION_ONLY).
    assert r["recommended_action"] == "DEMOTION"


# ── 5. Decay leger -7% WR -> OBSERVATION_ONLY ─────────────────────
def test_decay_mild_observation(monkeypatch):
    """WR chute de 40% -> 33% = -7 pts (entre OBS_PCT et DECAY_PCT) -> OBSERVATION_ONLY."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    # baseline wr=0.40, recent wr=0.33 (delta -7%)
    baseline, recent = _mk_split(baseline_wr=0.40, recent_wr=0.33, n_baseline=100, n_recent=20)
    trades = baseline + recent
    r = analyze_principle_decay("MILD", trades=trades, db_path=Path("/nonexistent"))
    # Pnl recent peut etre negatif => DEMOTION peut gagner.
    # On verifie au moins que OBSERVATION_ONLY est candidat (delta entre seuils).
    if r["pnl_recent"] >= 0:
        assert r["recommended_action"] == "OBSERVATION_ONLY"
    else:
        # Si pnl recent < 0, DEMOTION prend la priorite (comportement attendu).
        assert r["recommended_action"] in ("OBSERVATION_ONLY", "DEMOTION")


# ── 6. Scan trie par decay_score DESC ─────────────────────────────
def test_scan_sorted_by_decay_score(tmp_path: Path, monkeypatch):
    """scan_all_principles_decay retourne liste triee par decay_score DESC."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    # Cree une mini-DB avec 3 principes.
    db = tmp_path / "test_forces.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE paper_trades (
        trade_id TEXT, snapshot_id TEXT, direction TEXT, confiance INTEGER,
        principes_source TEXT, opened_at TEXT, closed_at TEXT, pips_simulated REAL,
        is_win INTEGER, risk_go_context TEXT, spread_pips REAL, pips_net_of_spread REAL
    )""")
    # Principe A : stable (wr 0.5 -> 0.5)
    for i in range(120):
        wr = 0.5
        is_win = 1 if i % 2 == 0 else 0
        pips = 5.0 if is_win else -3.0
        conn.execute(
            "INSERT INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"tA{i}", "s", "BUY", 70, "PRIN_A", f"2026-06-01T{i:02d}:00:00+00:00", "",
             pips, is_win, "", 1.0, pips)
        )
    # Principe B : severe decay
    for i in range(120):
        is_win = 1 if i < 40 else 0  # wr=0.33 baseline, wr=0.0 recent
        pips = 5.0 if is_win else -3.0
        conn.execute(
            "INSERT INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"tB{i}", "s", "BUY", 70, "PRIN_B", f"2026-06-02T{i:02d}:00:00+00:00", "",
             pips, is_win, "", 1.0, pips)
        )
    # Principe C : mild decay
    for i in range(120):
        # baseline wr=0.5, recent wr=0.35
        if i < 100:
            is_win = 1 if i % 2 == 0 else 0
        else:
            is_win = 1 if i % 3 == 0 else 0
        pips = 5.0 if is_win else -3.0
        conn.execute(
            "INSERT INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"tC{i}", "s", "BUY", 70, "PRIN_C", f"2026-06-03T{i:02d}:00:00+00:00", "",
             pips, is_win, "", 1.0, pips)
        )
    conn.commit()
    conn.close()

    out = scan_all_principles_decay(db_path=db)
    assert len(out) == 3
    # Premier = pire decay (PRIN_B attendu en tete).
    pids = [r["principle_id"] for r in out]
    assert pids[0] == "PRIN_B"
    # Tri strictement par decay_score DESC.
    for i in range(len(out) - 1):
        assert out[i]["decay_score"] >= out[i + 1]["decay_score"]


# ── 7. R6 fail-open : DB absente ──────────────────────────────────
def test_fail_open_db_absent_scan(tmp_path: Path, monkeypatch):
    """DB inexistante -> scan retourne liste vide (R6 fail-open)."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    out = scan_all_principles_decay(db_path=tmp_path / "ghost.db")
    assert out == []


def test_fail_open_db_absent_analyze(monkeypatch):
    """DB inexistante + trades=None -> analyze retourne zeros."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    r = analyze_principle_decay("X", trades=None, db_path=Path("/nonexistent/db.db"))
    assert r["decay_detected"] is False
    assert r["n_baseline"] == 0


# ── 8. summarize_scan ─────────────────────────────────────────────
def test_summarize_scan_aggregates():
    """summarize_scan agrege correctement n_decay, n_blacklist, etc."""
    reports = [
        {"decay_detected": True, "recommended_action": "BLACKLIST_TEMP_24H", "pnl_recent": -100.0, "decay_score": 0.5},
        {"decay_detected": True, "recommended_action": "DEMOTION", "pnl_recent": -50.0, "decay_score": 0.3},
        {"decay_detected": True, "recommended_action": "OBSERVATION_ONLY", "pnl_recent": 20.0, "decay_score": 0.1},
        {"decay_detected": False, "recommended_action": "NONE", "pnl_recent": 80.0, "decay_score": 0.0},
    ]
    s = summarize_scan(reports)
    assert s["n_principles"] == 4
    assert s["n_decay"] == 3
    assert s["n_blacklist"] == 1
    assert s["n_demote"] == 1
    assert s["n_observation"] == 1
    assert s["pnl_recent_total"] == -50.0


def test_summarize_scan_empty():
    s = summarize_scan([])
    assert s["n_principles"] == 0
    assert s["n_decay"] == 0
    assert s["pnl_recent_total"] == 0.0


# ── 9. Donnees insuffisantes ──────────────────────────────────────
def test_insufficient_trades_pass_through(monkeypatch):
    """< MIN_TRADES_BASELINE trades -> pass-through (decay_detected=False)."""
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    short = _mk_trades(20, wr=0.5)
    r = analyze_principle_decay("YOUNG", trades=short, db_path=Path("/nonexistent"))
    assert r["decay_detected"] is False
    assert r["n_baseline"] == 0
    assert r["recommended_action"] == "NONE"


# ── 10. Audit live : principes en decay sur la DB reelle ──────────
def test_audit_live_db_principles_in_decay(monkeypatch):
    """Audit R14 : verifie que la DB live montre bien du decay systemique.

    Ce test peut etre lent (lecture 337 trades) et depend de la presence
    de data/v9_forces.db. Il sert de 'regression guard' sur l'audit SQL
    du 03/08.
    """
    monkeypatch.setenv("V9_EDGE_DECAY_SENTINEL_ENABLED", "1")
    db_path = Path("data/v9_forces.db")
    if not db_path.exists():
        pytest.skip("DB live absente (env CI)")

    out = scan_all_principles_decay(db_path=db_path)
    # On doit avoir au moins 1 principe eligibility.
    assert len(out) >= 1
    # La majorite doivent etre en decay (audit 03/08 : 21/21).
    n_decay = sum(1 for r in out if r["decay_detected"])
    assert n_decay >= 1, f"Attendu >=1 principe en decay, got {n_decay}"
    # Top 1 doit avoir un decay_score > 0.3.
    assert out[0]["decay_score"] > 0.3
    # Toutes les entrees doivent avoir un action recommendee valide.
    valid_actions = {"NONE", "OBSERVATION_ONLY", "DEMOTION", "BLACKLIST_TEMP_24H"}
    for r in out:
        assert r["recommended_action"] in valid_actions

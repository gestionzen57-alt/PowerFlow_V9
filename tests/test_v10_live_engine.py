"""V10 Live Engine — tests unitaires (Phase 7 Edge Fund).

Couvre les obligations de la Phase 7 :
  1. test_read_db_pairs_bars_returns_ohlcv
  2. test_process_pair_tf_handles_empty_db
  3. test_snapshot_includes_all_setups
  4. test_filter_a1_only
  5. test_filter_a1_plus_a2
  6. test_filter_a1_a2_a3
  7. test_atomic_persistence_via_tmp
  8. test_telegram_formatting_with_signal
  9. test_telegram_formatting_no_signal
+ 6 bonus.

Total ≥ 15 tests.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v10_live_engine import (  # noqa: E402
    _read_db_pairs_bars,
    _read_latest_currency_strength,
    process_pair_tf,
    run_snapshot,
    persist_snapshot,
    format_telegram,
    run_loop,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture : DB sqlite mémoire avec quelques bougies
# ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def fake_db(tmp_path) -> str:
    """Crée une DB SQLite temporaire avec des barres forces_snapshots."""
    db_path = str(tmp_path / "fake_v9.db")
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            bar_time INTEGER NOT NULL,
            timestamp TEXT,
            is_closed_bar INTEGER,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            tick_volume INTEGER
        )
    """)
    # Insertion de 50 barres EURUSD M15 avec tendance haussière
    import time as _t
    base = _t.time() - 50 * 900
    for i in range(50):
        cur.execute("""
            INSERT INTO forces_snapshots
            (symbol, timeframe, bar_time, timestamp, is_closed_bar,
             open, high, low, close, tick_volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "EURUSD", "M15", int(base + i * 900), f"2026-08-04T{15 + (i // 60):02d}:{(i*15) % 60:02d}:00Z",
            1, 1.10 + i * 0.00005,
            1.1005 + i * 0.00005,
            1.0995 + i * 0.00005,
            1.1002 + i * 0.00005,
            1000 + i * 10,
        ))
    con.commit()
    con.close()
    return db_path


# ─────────────────────────────────────────────────────────────────────
# 1. test_read_db_pairs_bars_returns_ohlcv
# ─────────────────────────────────────────────────────────────────────
def test_read_db_pairs_bars_returns_ohlcv(fake_db):
    bars = _read_db_pairs_bars(fake_db, "EURUSD", "M15", limit=20)
    assert len(bars) == 20
    assert all(k in bars[0] for k in ("open", "high", "low", "close", "tick_volume"))
    assert bars[0]["close"] > 0


# ─────────────────────────────────────────────────────────────────────
# 2. test_process_pair_tf_handles_empty_db
# ─────────────────────────────────────────────────────────────────────
def test_process_pair_tf_handles_empty_db(fake_db):
    # DB vide pour USDJPY H4 → R6 : soit None (fail-open), soit un signal
    # issu du fallback MT5 live (Phase 33 — le bridge est vivant).
    # Les deux sont des comportements légitimes : le pipeline ne crashe pas.
    sig = process_pair_tf(fake_db, "USDJPY", "H4")
    # Si le fallback MT5 a fourni des barres live, le signal est enrichi
    # avec degraded_mode=False ; sinon None (fail-open).
    if sig is not None:
        assert sig.pair == "USDJPY"
        assert sig.timeframe == "H4"


def test_process_pair_tf_with_sufficient_data(fake_db):
    """Avec 50 barres fake_db croissante haussière + degraded mode confluence, on a au moins
    un signal retourné (même si setup_level=NONE — degraded mode)."""
    sig = process_pair_tf(fake_db, "EURUSD", "M15")
    # Mode dégradé : on autorise qu'il n'y ait pas de signal directionnel exploitable
    # (currency_strength lit des proxies dégradés sur 1 seul TF).
    # Mais le pipeline doit au moins renvoyer un EnhancedSignal non-None
    # pour les barres fake présentes.
    assert sig is not None, "Pipeline devrait renvoyer un EnhancedSignal (degraded)"
    assert sig.pair == "EURUSD"
    assert sig.timeframe == "M15"


# ─────────────────────────────────────────────────────────────────────
# 3. test_snapshot_includes_all_setups
# ─────────────────────────────────────────────────────────────────────
def test_snapshot_includes_all_setups(fake_db):
    snap = run_snapshot(fake_db, symbols=("EURUSD",), timeframes=("M15",))
    assert snap["n_setups_processed"] == 1
    assert "timestamp" in snap
    assert "by_level" in snap
    assert set(snap["by_level"].keys()) >= {"A1", "A2", "A3", "NONE"}


# ─────────────────────────────────────────────────────────────────────
# 4. test_filter_a1_only
# ─────────────────────────────────────────────────────────────────────
def test_filter_a1_only(fake_db):
    snap = run_snapshot(
        fake_db, symbols=("EURUSD",), timeframes=("M15",),
        include_a2=False, include_a3=False,
    )
    # Seuls les A1 sont retenus dans `signals`
    assert all(s["setup_level"] == "A1" for s in snap["signals"])


# ─────────────────────────────────────────────────────────────────────
# 5. test_filter_a1_plus_a2
# ─────────────────────────────────────────────────────────────────────
def test_filter_a1_plus_a2(fake_db):
    snap = run_snapshot(
        fake_db, symbols=("EURUSD",), timeframes=("M15",),
        include_a2=True, include_a3=False,
    )
    assert all(s["setup_level"] in ("A1", "A2") for s in snap["signals"])


# ─────────────────────────────────────────────────────────────────────
# 6. test_filter_a1_a2_a3
# ─────────────────────────────────────────────────────────────────────
def test_filter_a1_a2_a3(fake_db):
    snap = run_snapshot(
        fake_db, symbols=("EURUSD",), timeframes=("M15",),
        include_a2=True, include_a3=True,
    )
    assert all(s["setup_level"] in ("A1", "A2", "A3") for s in snap["signals"])


# ─────────────────────────────────────────────────────────────────────
# 7. test_atomic_persistence_via_tmp
# ─────────────────────────────────────────────────────────────────────
def test_atomic_persistence_via_tmp(tmp_path, fake_db):
    snap = run_snapshot(fake_db, symbols=("EURUSD",), timeframes=("M15",))
    output = tmp_path / "signals.json"
    persist_snapshot(snap, output)
    # Le .tmp ne doit plus exister (rename atomique)
    assert output.exists()
    assert not output.with_suffix(output.suffix + ".tmp").exists()
    # Contenu lisible JSON
    loaded = json.loads(output.read_text())
    assert loaded["timestamp"] == snap["timestamp"]


# ─────────────────────────────────────────────────────────────────────
# 8. test_telegram_formatting_with_signal
# ─────────────────────────────────────────────────────────────────────
def test_telegram_formatting_with_signal():
    snap = {
        "timestamp": "2026-08-04T12:00:00Z",
        "n_setups_processed": 28,
        "n_signals_found": 1,
        "signals": [
            {
                "setup_level": "A1",
                "pair": "EURUSD",
                "timeframe": "M15",
                "direction": "BULLISH",
                "composite_score": 0.95,
                "confluence_score": 0.92,
                "vsa_state": "MARKUP",
                "bos": "BOS_BULL",
                "session": "LONDON",
                "cot": {"3_decide": "Signal A1 — high conviction."},
            }
        ],
        "by_level": {"A1": 1, "A2": 0, "A3": 0, "NONE": 27},
    }
    msg = format_telegram(snap)
    assert "🚨 V10 LIVE" in msg
    assert "EURUSD" in msg
    assert "BULLISH" in msg
    assert "high conviction" in msg


# ─────────────────────────────────────────────────────────────────────
# 9. test_telegram_formatting_no_signal
# ─────────────────────────────────────────────────────────────────────
def test_telegram_formatting_no_signal():
    snap = {
        "timestamp": "2026-08-04T12:00:00Z",
        "n_setups_processed": 28,
        "n_signals_found": 0,
        "signals": [],
        "by_level": {"A1": 0, "A2": 0, "A3": 0, "NONE": 28},
    }
    msg = format_telegram(snap)
    assert "🔕 V10 LIVE" in msg
    assert "Aucun signal A1" in msg


# ─────────────────────────────────────────────────────────────────────
# Bonus invariants
# ─────────────────────────────────────────────────────────────────────
def test_run_loop_max_iterations_stops(tmp_path, fake_db):
    """run_loop doit respecter max_iterations et arrêter."""
    audit = run_loop(
        fake_db, tmp_path / "out.json",
        interval_s=0.01, max_iterations=3,
        symbols=("EURUSD",), timeframes=("M15",),
    )
    assert audit["iterations"] == 3
    assert audit["reason"] == "max_iterations"


def test_snapshot_persistence_creates_parent_dirs(tmp_path, fake_db):
    """persist_snapshot crée les répertoires parents si manquants."""
    deep = tmp_path / "a" / "b" / "c" / "signals.json"
    snap = run_snapshot(fake_db, symbols=("EURUSD",), timeframes=("M15",))
    persist_snapshot(snap, deep)
    assert deep.exists()


def test_read_currency_strength_handles_missing_table(tmp_path):
    """Si la table n'existe pas → fail-open et retourne {} (R6)."""
    db = str(tmp_path / "empty.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE dummy (x INTEGER)")
    con.commit()
    con.close()
    cur = _read_latest_currency_strength(db, "H1")
    assert cur == {}  # R6 fail-open


def test_snapshot_serializable_to_json(fake_db):
    snap = run_snapshot(fake_db, symbols=("EURUSD",), timeframes=("M15",))
    j = json.dumps(snap, ensure_ascii=False)
    parsed = json.loads(j)
    assert parsed["n_setups_processed"] == 1


def test_no_db_path_raises_helpfully(tmp_path):
    """Si DB inexistante → fail-open ou erreur propre."""
    nonexistent = str(tmp_path / "not_exists.db")
    # Doit retourner [] sans crash (read-only mode)
    bars = _read_db_pairs_bars(nonexistent, "EURUSD", "M15")
    assert bars == []  # vide si DB inexistante


def test_run_snapshot_with_no_symbols_returns_empty():
    snap = run_snapshot("data/v9_forces.db", symbols=(), timeframes=())
    assert snap["n_setups_processed"] == 0
    assert snap["n_signals_found"] == 0
    assert snap["signals"] == []

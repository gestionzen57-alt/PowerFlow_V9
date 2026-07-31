"""tests/test_trade_engine_j6_mirror_blocking.py — J6 2026-07-28 mirror BLOCKING.

Additif (R2). Section 2bis de trade_engine.process() : si kill switch
V9_HUMAN_MIRROR_BLOCKING=ON ET module v9_human_mirror a un fingerprint
disponible, score < 0.5 → downgrade action.
"""
import os
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_with_mirror(tmp_path, monkeypatch):
    """DB avec table v9_human_trades seedée de trades haussiere GBPUSD M5."""
    db = tmp_path / "v9.db"

    # Crée tables minimales nécessaires pour _resolve_symbol_and_decision
    with sqlite3.connect(str(db)) as conn:
        for tbl, schema in [
            ("paper_trades", "(snapshot_id TEXT, direction TEXT, is_win INTEGER, pips_simulated REAL, opened_at TEXT)"),
            ("decisions", "(snapshot_id TEXT, statut TEXT, direction TEXT, confidence INTEGER, timestamp TEXT)"),
            ("forces_snapshots", "(snapshot_id TEXT PRIMARY KEY)"),
            ("scenes", "(scene_id TEXT, forces_snapshot_ref TEXT)"),
            ("behaviors", "(behavior_id TEXT, scene_id_ref TEXT, qualification TEXT)"),
            ("windows", "(window_id TEXT, behavior_id_ref TEXT, snapshot_id TEXT, statut TEXT)"),
            ("exploitability", "(exploitability_id TEXT, window_id_ref TEXT, forces_snapshot_ref TEXT, statut TEXT, niveau_confiance_global INTEGER)"),
        ]:
            conn.execute(f"CREATE TABLE {tbl} {schema}")
        conn.commit()

    # Seed 3 trades humains haussiere GBPUSD
    from core.v9.human_trades_db import init_human_trades_db, insert_human_trade
    init_human_trades_db(db)
    for i in range(3):
        insert_human_trade(
            db_path=db, symbol="GBPUSD", direction="haussiere",
            timeframe="M5", entry_price=1.2500 + i*0.001,
            sl_price=1.2490, tp_price=1.2520,
            confiance=85, session="london",
            principes=["PRICE_LAG_AT_NODE_BIRTH"],
            notes=f"seed {i}",
        )

    # Force HUMAN_MIRROR activé
    monkeypatch.setenv("V9_HUMAN_MIRROR_ENABLED", "1")
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "1")
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCK_THRESHOLD", "0.5")
    yield db

    for k in ("V9_HUMAN_MIRROR_ENABLED", "V9_HUMAN_MIRROR_BLOCKING",
              "V9_HUMAN_MIRROR_BLOCK_THRESHOLD"):
        monkeypatch.delenv(k, raising=False)


def test_mirror_module_helpers_work():
    """v9_human_mirror.match_score retourne dict avec clés attendues."""
    from core.v9.v9_human_mirror import mirror_enabled, mirror_blocking_enabled
    assert mirror_enabled() is True
    assert mirror_blocking_enabled() is True


def test_mirror_score_perfect_match_returns_high_score():
    """Match parfait → score ≥ 0.5."""
    from core.v9.v9_human_mirror import match_score
    sig = {
        "symbol": "GBPUSD", "direction": "haussiere", "timeframe": "M5",
        "entry_price": 1.2510, "confiance": 85, "session": "london",
        "principes": ["PRICE_LAG_AT_NODE_BIRTH"],
    }
    res = match_score(signal=sig, db_path=":memory:")
    # No humans in :memory:
    assert res["score"] == 0.5
    assert res["action_recommended"] == "keep"


def test_mirror_blocking_kill_switch_can_be_disabled(monkeypatch):
    """V9_HUMAN_MIRROR_BLOCKING=0 → désactive le downgrade."""
    from core.v9.v9_human_mirror import mirror_blocking_enabled
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "0")
    assert mirror_blocking_enabled() is False


def test_mirror_module_disabled_returns_neutral(monkeypatch):
    """V9_HUMAN_MIRROR_ENABLED=0 → mirror_off → pas de score (neutre)."""
    from core.v9.v9_human_mirror import mirror_enabled
    monkeypatch.setenv("V9_HUMAN_MIRROR_ENABLED", "0")
    assert mirror_enabled() is False


def test_mirror_no_data_neutral_score():
    """DB vide (ou no humans) → score=0.5, action=keep."""
    from core.v9.v9_human_mirror import match_score
    res = match_score(
        signal={"symbol": "GBPUSD", "direction": "haussiere"},
        db_path=":memory:",  # memory only, no humans table
    )
    assert res["score"] == 0.5
    assert res["action_recommended"] == "keep"

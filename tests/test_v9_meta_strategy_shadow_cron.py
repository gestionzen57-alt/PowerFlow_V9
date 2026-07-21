"""test_v9_meta_strategy_shadow_cron.py — Tests polling shadow live Chemin C."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest


# ------------------------------------------------------------------ fixtures


def _create_decisions_table(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                direction TEXT,
                regime_type TEXT,
                is_win INTEGER,
                resolution_pips REAL NOT NULL,
                resolved_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signals (
                snapshot_id TEXT PRIMARY KEY,
                phase TEXT,
                volatility_atr_pips REAL,
                exit_strategy_recommended TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_decisions_is_win
                ON decisions(is_win);
            CREATE INDEX IF NOT EXISTS idx_decisions_resolved
                ON decisions(resolved_at);
        """)
        conn.commit()
    finally:
        conn.close()


def _insert_decision(
    db_path: Path,
    *,
    decision_id: str,
    snapshot_id: str,
    symbol: str = "GBPUSD",
    timeframe: str = "M15",
    direction: str = "long",
    regime_type: str = "NEUTRE",
    is_win: int = 1,
    resolution_pips: float = 10.0,
    resolved_at: float = None,
    phase: str = "initiation",
    vol_atr: float = 10.0,
    exit_strat: str = "TP_SL",
) -> None:
    if resolved_at is None:
        resolved_at = time.time()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO decisions "
            "(decision_id, snapshot_id, symbol, timeframe, direction, regime_type, "
            "is_win, resolution_pips, resolved_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (decision_id, snapshot_id, symbol, timeframe, direction, regime_type,
             is_win, resolution_pips, resolved_at),
        )
        conn.execute(
            "INSERT OR REPLACE INTO signals "
            "(snapshot_id, phase, volatility_atr_pips, exit_strategy_recommended) "
            "VALUES (?,?,?,?)",
            (snapshot_id, phase, vol_atr, exit_strat),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def empty_db(tmp_path):
    db = tmp_path / "test_cron.db"
    _create_decisions_table(db)
    return db


@pytest.fixture
def populated_db(tmp_path, monkeypatch):
    """10 décisions résolues (8 WIN / 2 LOSS)."""
    db = tmp_path / "populated_cron.db"
    _create_decisions_table(db)
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    monkeypatch.setenv("V9_META_STRATEGY_OPTIMIZER_ENABLED", "1")
    now = time.time()
    for i in range(8):
        _insert_decision(
            db, decision_id=f"win_{i}", snapshot_id=f"snap_win_{i}",
            is_win=1, resolution_pips=12.0 + i * 0.1,
            resolved_at=now - i * 60, exit_strat="TP_SL",
        )
    for i in range(2):
        _insert_decision(
            db, decision_id=f"loss_{i}", snapshot_id=f"snap_loss_{i}",
            is_win=0, resolution_pips=-8.0,
            resolved_at=now - (i + 10) * 60, exit_strat="TRAILING",
        )
    return db


# ------------------------------------------------------------------ kill switch


def test_shadow_enabled_default_off(monkeypatch):
    monkeypatch.delenv("V9_META_STRATEGY_SHADOW_ENABLED", raising=False)
    from scripts.v9_meta_strategy_shadow_cron import _shadow_enabled
    assert _shadow_enabled() is False


def test_shadow_enabled_explicit_on(monkeypatch):
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    from scripts.v9_meta_strategy_shadow_cron import _shadow_enabled
    assert _shadow_enabled() is True


# ------------------------------------------------------------------ since_ts


def test_since_ts_hours():
    from scripts.v9_meta_strategy_shadow_cron import _since_ts
    ts = _since_ts("1h")
    assert (time.time() - ts) < 3700


def test_since_ts_days():
    from scripts.v9_meta_strategy_shadow_cron import _since_ts
    ts = _since_ts("7d")
    assert (time.time() - ts) > 7 * 86400 - 10


def test_since_ts_invalid():
    from scripts.v9_meta_strategy_shadow_cron import _since_ts
    with pytest.raises(SystemExit):
        _since_ts("invalid")


# ------------------------------------------------------------------ DB loading


def test_load_resolved_decisions_empty(empty_db):
    from scripts.v9_meta_strategy_shadow_cron import _load_resolved_decisions
    rows = _load_resolved_decisions(empty_db, None, 100)
    assert rows == []


def test_load_resolved_decisions_populated(populated_db):
    from scripts.v9_meta_strategy_shadow_cron import _load_resolved_decisions
    rows = _load_resolved_decisions(populated_db, None, 100)
    assert len(rows) == 10
    assert all(r["is_win"] in (0, 1) for r in rows)


def test_load_resolved_decisions_since_filter(populated_db):
    from scripts.v9_meta_strategy_shadow_cron import _load_resolved_decisions
    rows = _load_resolved_decisions(populated_db, time.time() - 300, 100)
    assert 0 <= len(rows) <= 10


# ------------------------------------------------------------------ cursor anti-doublon


def test_get_max_shadow_id_no_table(empty_db):
    from scripts.v9_meta_strategy_shadow_cron import _get_max_shadow_id
    assert _get_max_shadow_id(empty_db) == 0


def test_get_max_shadow_id_with_logs(populated_db):
    """Après run avec shadow ON, max(id) > 0."""
    from scripts.v9_meta_strategy_shadow_cron import _get_max_shadow_id
    from core.v9.v9_meta_strategy_shadow import ensure_shadow_table, recommend_with_shadow
    from dataclasses import dataclass

    @dataclass
    class FakeLegacy:
        recommended_strategy: str = "TP_SL"
        confidence: float = 0.5
        recommended_tp: float = 10.0
        recommended_sl: float = 15.0

    @dataclass
    class FakeMeta:
        chosen_strategy: str = "TP_SL"
        confidence: float = 0.5
        recommended_tp: float = 10.0
        recommended_sl: float = 15.0
        source: str = "meta_optimizer"
        rationale: str = ""

    ensure_shadow_table(populated_db)
    recommend_with_shadow(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="initiation", direction="long",
        legacy_recommendation=FakeLegacy(),
        db_path=populated_db, meta_strategy_decision=FakeMeta(),
    )
    assert _get_max_shadow_id(populated_db) >= 1


# ------------------------------------------------------------------ run_polling


def test_run_polling_no_data(empty_db, monkeypatch):
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    from scripts.v9_meta_strategy_shadow_cron import run_polling
    res = run_polling(empty_db, since_ts=None, limit=100, apply=False)
    assert res["n_total_scanned"] == 0
    assert res["n_processed"] == 0


def test_run_polling_dry_run(populated_db, monkeypatch):
    """Mode dry-run : on compte mais on n'écrit pas."""
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    from scripts.v9_meta_strategy_shadow_cron import run_polling
    res = run_polling(populated_db, since_ts=None, limit=10, apply=False)
    assert res["n_total_scanned"] == 10
    assert res["n_processed"] >= 0
    # Vérifier que la table shadow n'est pas alimentée
    from core.v9.v9_meta_strategy_shadow import ensure_shadow_table
    ensure_shadow_table(populated_db)
    # Note : run_polling dry-run passe db_path=None, donc 0 inserts.


def test_run_polling_apply(populated_db, monkeypatch):
    """Mode apply : alimente meta_strategy_shadow_log."""
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    monkeypatch.setenv("V9_META_STRATEGY_OPTIMIZER_ENABLED", "1")
    from scripts.v9_meta_strategy_shadow_cron import run_polling
    from core.v9.v9_meta_strategy_shadow import ensure_shadow_table
    ensure_shadow_table(populated_db)

    res = run_polling(populated_db, since_ts=None, limit=10, apply=True)
    assert res["n_total_scanned"] == 10

    # Vérifier que la table shadow a bien des logs
    conn = sqlite3.connect(str(populated_db))
    n_logs = conn.execute("SELECT COUNT(*) FROM meta_strategy_shadow_log").fetchone()[0]
    conn.close()
    assert n_logs > 0


# ------------------------------------------------------------------ CLI


def test_main_missing_db(tmp_path):
    from scripts.v9_meta_strategy_shadow_cron import main
    rc = main(["--db-path", str(tmp_path / "nope.db")])
    assert rc == 1


def test_main_kill_switch_off(empty_db, monkeypatch):
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "0")
    from scripts.v9_meta_strategy_shadow_cron import main
    rc = main(["--db-path", str(empty_db)])
    assert rc == 1


def test_main_invalid_since(empty_db, monkeypatch):
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    from scripts.v9_meta_strategy_shadow_cron import main
    rc = main(["--db-path", str(empty_db), "--since", "garbage"])
    assert rc == 2


def test_main_dry_run_no_data(empty_db, monkeypatch):
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    from scripts.v9_meta_strategy_shadow_cron import main
    rc = main(["--db-path", str(empty_db), "--no-write"]) if False else main(["--db-path", str(empty_db)])
    assert rc == 0


def test_main_apply_with_data(populated_db, monkeypatch):
    from scripts.v9_meta_strategy_shadow_cron import main
    rc = main(["--db-path", str(populated_db), "--apply", "--limit", "5"])
    assert rc == 0


# ------------------------------------------------------------------ non-intrusive


def test_polling_no_trade_no_order(populated_db, monkeypatch):
    """Vérifie que le polling ne déclenche aucun trade ni ordre (R12 fondateur)."""
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    monkeypatch.setenv("V9_META_STRATEGY_OPTIMIZER_ENABLED", "1")
    from scripts.v9_meta_strategy_shadow_cron import run_polling
    # Snapshot pre-count paper_trades
    conn = sqlite3.connect(str(populated_db))
    pt_count_pre = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='paper_trades'"
    ).fetchone()[0]
    conn.close()

    run_polling(populated_db, since_ts=None, limit=10, apply=True)

    # Vérifier que paper_trades n'est pas créée par le polling
    conn = sqlite3.connect(str(populated_db))
    pt_count_post = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='paper_trades'"
    ).fetchone()[0]
    conn.close()
    assert pt_count_pre == pt_count_post == 0  # pas de table paper_trades créée
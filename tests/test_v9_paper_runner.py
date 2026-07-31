"""tests/test_v9_paper_runner.py — Phase 16 motion CEO « EDGE FUND MAX ».

Paper-trading continu automatise : table v9_paper_trades + log events.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture
def db_with_snapshots(tmp_path):
    """Cree une DB avec table forces_snapshots minimaliste."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE forces_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, timestamp TEXT, mid REAL,
                symbol TEXT, timeframe TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE regime_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regime_id TEXT, forces_snapshot_ref TEXT,
                symbol TEXT, timeframe TEXT, regime_type TEXT,
                vol_regime TEXT
            )
        """)
        # 3 snapshots recents
        now = datetime.now(timezone.utc)
        for i in range(3):
            conn.execute("""
                INSERT INTO forces_snapshots
                (snapshot_id, timestamp, mid, symbol, timeframe)
                VALUES (?, ?, ?, 'GBPUSD', 'M5')
            """, (f"v9-GBPUSD-M5-{i}", (now - timedelta(minutes=i*5)).isoformat(),
                  1.2680 + i * 0.0001))
        conn.commit()
    return db


def test_ensure_tables_idempotent(db_with_snapshots):
    """_ensure_tables cree v9_paper_trades + v9_paper_log (idempotent)."""
    from scripts.v9_paper_runner import _ensure_tables
    _ensure_tables(db_with_snapshots)
    _ensure_tables(db_with_snapshots)  # idempotent
    with sqlite3.connect(str(db_with_snapshots)) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "v9_paper_trades" in tables
    assert "v9_paper_log" in tables


def test_ensure_tables_missing_db(tmp_path):
    """_ensure_tables sur DB absente → no-op (degrade)."""
    from scripts.v9_paper_runner import _ensure_tables
    _ensure_tables(tmp_path / "absent.db")  # pas d'exception


def test_get_recent_snapshots_returns_3(db_with_snapshots):
    """get_recent_snapshots retourne les 3 snapshots GBPUSD."""
    from scripts.v9_paper_runner import get_recent_snapshots
    snaps = get_recent_snapshots(db_with_snapshots, lookback_minutes=60)
    assert len(snaps) == 3
    assert all(s["symbol"] == "GBPUSD" for s in snaps)


def test_get_recent_snapshots_missing_db(tmp_path):
    """get_recent_snapshots sur DB absente → []."""
    from scripts.v9_paper_runner import get_recent_snapshots
    snaps = get_recent_snapshots(tmp_path / "absent.db")
    assert snaps == []


def test_get_recent_snapshots_filters_other_symbols(tmp_path):
    """get_recent_snapshots filtre les autres symbols."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE forces_snapshots (
                snapshot_id TEXT, timestamp TEXT, mid REAL,
                symbol TEXT, timeframe TEXT
            )
        """)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO forces_snapshots VALUES (?, ?, ?, ?, ?)",
                     ("v9-GBPUSD-M5-1", now, 1.2680, "GBPUSD", "M5"))
        conn.execute("INSERT INTO forces_snapshots VALUES (?, ?, ?, ?, ?)",
                     ("v9-EURUSD-M5-1", now, 1.0850, "EURUSD", "M5"))
        conn.commit()
    from scripts.v9_paper_runner import get_recent_snapshots
    snaps = get_recent_snapshots(db, symbol="GBPUSD")
    assert len(snaps) == 1
    assert snaps[0]["symbol"] == "GBPUSD"


def test_count_open_paper_trades_zero(db_with_snapshots):
    """count_open_paper_trades = 0 si pas de trades."""
    from scripts.v9_paper_runner import _ensure_tables, count_open_paper_trades
    _ensure_tables(db_with_snapshots)
    assert count_open_paper_trades(db_with_snapshots) == 0


def test_open_and_count_paper_trade(db_with_snapshots):
    """open_paper_trade + count_open_paper_trades."""
    from scripts.v9_paper_runner import (
        _ensure_tables, open_paper_trade, count_open_paper_trades,
    )
    _ensure_tables(db_with_snapshots)
    trade_id = open_paper_trade(
        db_with_snapshots,
        snapshot_id="v9-GBPUSD-M5-1",
        symbol="GBPUSD", direction="haussiere",
        entry_price=1.2680, tp_pips=25, sl_pips=8, lot=0.01,
        leviers=["L1", "L4"], confidence=1.5,
    )
    assert trade_id > 0
    assert count_open_paper_trades(db_with_snapshots) == 1


def test_close_paper_trade(db_with_snapshots):
    """close_paper_trade met a jour close_reason + pips."""
    from scripts.v9_paper_runner import (
        _ensure_tables, open_paper_trade, close_paper_trade,
        count_open_paper_trades,
    )
    _ensure_tables(db_with_snapshots)
    trade_id = open_paper_trade(
        db_with_snapshots, snapshot_id="v9-GBPUSD-M5-1",
        symbol="GBPUSD", direction="haussiere", entry_price=1.2680,
    )
    close_paper_trade(
        db_with_snapshots, trade_id,
        close_reason="TP_hit", close_price=1.2705,
        pips_brut=25.0, pips_net=23.5, spread_pips=1.5,
    )
    assert count_open_paper_trades(db_with_snapshots) == 0
    with sqlite3.connect(str(db_with_snapshots)) as conn:
        row = conn.execute("""
            SELECT pips_brut, pips_net, close_reason FROM v9_paper_trades
            WHERE id=?
        """, (trade_id,)).fetchone()
    assert row[0] == 25.0
    assert row[1] == 23.5
    assert row[2] == "TP_hit"


def test_close_expired_trades(db_with_snapshots):
    """close_expired_trades ferme les trades > 5min (L3 time_exit)."""
    from scripts.v9_paper_runner import (
        _ensure_tables, open_paper_trade, close_expired_trades,
        count_open_paper_trades,
    )
    _ensure_tables(db_with_snapshots)
    # Trade ouvert il y a 10 min (expire)
    conn = sqlite3.connect(str(db_with_snapshots))
    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    conn.execute("""
        INSERT INTO v9_paper_trades
        (snapshot_id, symbol, direction, opened_at, entry_price)
        VALUES (?, 'GBPUSD', 'haussiere', ?, 1.2680)
    """, ("v9-GBPUSD-M5-old", old_ts))
    conn.commit()
    conn.close()

    n_closed = close_expired_trades(db_with_snapshots, max_hold_minutes=5.0)
    assert n_closed == 1
    assert count_open_paper_trades(db_with_snapshots) == 0


def test_close_expired_no_op_for_fresh_trades(db_with_snapshots):
    """close_expired_trades ne ferme pas les trades recents."""
    from scripts.v9_paper_runner import (
        _ensure_tables, open_paper_trade, close_expired_trades,
    )
    _ensure_tables(db_with_snapshots)
    open_paper_trade(
        db_with_snapshots, snapshot_id="v9-GBPUSD-M5-1",
        symbol="GBPUSD", direction="haussiere", entry_price=1.2680,
    )
    n_closed = close_expired_trades(db_with_snapshots, max_hold_minutes=5.0)
    assert n_closed == 0


def test_get_status_empty(db_with_snapshots):
    """get_status sur DB vide → n_open=0, n_total=0, wr=0."""
    from scripts.v9_paper_runner import _ensure_tables, get_status
    _ensure_tables(db_with_snapshots)
    status = get_status(db_with_snapshots)
    assert status["n_open"] == 0
    assert status["n_total"] == 0
    assert status["wr_pct"] == 0.0


def test_get_status_with_trades(db_with_snapshots):
    """get_status calcule WR apres quelques trades."""
    from scripts.v9_paper_runner import (
        _ensure_tables, open_paper_trade, close_paper_trade, get_status,
    )
    _ensure_tables(db_with_snapshots)
    # 2 wins + 1 loss
    for i, pips in enumerate([25.0, 25.0, -8.0]):
        tid = open_paper_trade(
            db_with_snapshots, snapshot_id=f"v9-GBPUSD-M5-{i}",
            symbol="GBPUSD", direction="haussiere", entry_price=1.2680,
        )
        close_paper_trade(
            db_with_snapshots, tid,
            close_reason="test", close_price=1.2680 + pips * 0.0001,
            pips_brut=pips, pips_net=pips - 1.5, spread_pips=1.5,
        )
    status = get_status(db_with_snapshots)
    assert status["n_closed"] == 3
    assert status["n_total"] == 3
    assert status["wr_pct"] == pytest.approx(66.67, abs=0.1)


def test_run_one_cycle_no_snapshots(db_with_snapshots):
    """run_one_cycle : no_snapshots si pas de forces_snapshots GBPUSD."""
    from scripts.v9_paper_runner import _ensure_tables, run_one_cycle
    _ensure_tables(db_with_snapshots)
    # Vider forces_snapshots
    with sqlite3.connect(str(db_with_snapshots)) as conn:
        conn.execute("DELETE FROM forces_snapshots")
        conn.commit()
    result = run_one_cycle(db_with_snapshots)
    assert result["cycle"] == "no_snapshots"


def test_run_one_cycle_completes(db_with_snapshots, monkeypatch):
    """run_one_cycle : complete avec decision go=True (mega_edge_evaluation)."""
    from scripts.v9_paper_runner import (
        _ensure_tables, run_one_cycle, count_open_paper_trades,
    )
    _ensure_tables(db_with_snapshots)
    # Mock mega_edge_evaluation pour forcer go=True
    monkeypatch.setattr(
        "scripts.v9_paper_runner.evaluate_signal",
        lambda db, sid, **kw: {
            "go": True, "reason": "test_mock",
            "leviers": ["L1"], "sizing_multiplier": 1.5,
        },
    )
    result = run_one_cycle(db_with_snapshots)
    assert result["cycle"] == "completed"
    assert result["n_new_trades"] >= 1
    assert count_open_paper_trades(db_with_snapshots) >= 1


def test_run_one_cycle_max_open_skips(db_with_snapshots, monkeypatch):
    """run_one_cycle : skipped si max_open atteint."""
    from scripts.v9_paper_runner import (
        _ensure_tables, open_paper_trade, run_one_cycle,
        MAX_OPEN_TRADES,
    )
    _ensure_tables(db_with_snapshots)
    for i in range(MAX_OPEN_TRADES):
        open_paper_trade(
            db_with_snapshots, snapshot_id=f"v9-GBPUSD-M5-open-{i}",
            symbol="GBPUSD", direction="haussiere", entry_price=1.2680,
        )
    result = run_one_cycle(db_with_snapshots)
    assert result["cycle"] == "skipped_max_open"
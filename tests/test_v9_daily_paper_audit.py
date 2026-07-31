"""tests/test_v9_daily_paper_audit.py — Phase 17 motion CEO « EDGE FUND MAX ».

Audit quotidien des paper_trades (Phase 16).
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def _create_db_with_paper_trades(db, trades):
    """Cree DB avec table v9_paper_trades et trades."""
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT,
                symbol TEXT,
                direction TEXT,
                opened_at TEXT,
                closed_at TEXT,
                entry_price REAL,
                tp_pips REAL,
                sl_pips REAL,
                lot REAL,
                close_reason TEXT,
                pips_brut REAL,
                pips_net REAL,
                spread_pips REAL
            )
        """)
        for trade in trades:
            conn.execute("""
                INSERT INTO v9_paper_trades
                (snapshot_id, symbol, direction, opened_at, closed_at,
                 pips_brut, pips_net, spread_pips)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, trade)
        conn.commit()


def test_audit_db_missing(tmp_path):
    """audit_paper_trades sur DB absente → error db_missing."""
    from scripts.v9_daily_paper_audit import audit_paper_trades
    res = audit_paper_trades(tmp_path / "absent.db")
    assert res["error"] == "db_missing"


def test_audit_empty_db(tmp_path):
    """audit_paper_trades sur DB vide → n_total=0, ready_live=False."""
    from scripts.v9_daily_paper_audit import audit_paper_trades
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        # Schema complet aligne sur scripts/v9_paper_runner.py
        conn.execute("""CREATE TABLE v9_paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT, symbol TEXT, direction TEXT,
            opened_at TEXT, closed_at TEXT, entry_price REAL,
            tp_pips REAL, sl_pips REAL, lot REAL, close_reason TEXT,
            pips_brut REAL, pips_net REAL, spread_pips REAL
        )""")
        conn.commit()
    res = audit_paper_trades(db)
    assert res["n_total"] == 0
    assert res["n_closed"] == 0
    assert res["wr_pct"] == 0
    assert res["ready_live"] is False
    assert res["recommendation"] == "WAIT_MORE_DATA"


def test_audit_with_25_winning_trades(tmp_path):
    """25 trades fermes (20 wins / 5 losses) → WR 80%."""
    from scripts.v9_daily_paper_audit import audit_paper_trades
    db = tmp_path / "v9.db"
    now = datetime.now(timezone.utc) - timedelta(hours=2)
    trades = []
    for i in range(20):
        opened = (now + timedelta(minutes=5 * i)).isoformat()
        closed = (now + timedelta(minutes=5 * i + 1)).isoformat()
        trades.append(("v9-test", "GBPUSD", "haussiere", opened, closed,
                       25.0, 23.5, 1.5))
    for i in range(5):
        opened = (now + timedelta(hours=1, minutes=10 * i)).isoformat()
        closed = (now + timedelta(hours=1, minutes=10 * i + 1)).isoformat()
        trades.append(("v9-test", "GBPUSD", "haussiere", opened, closed,
                       -8.0, -9.5, 1.5))
    _create_db_with_paper_trades(db, trades)
    res = audit_paper_trades(db)
    assert res["n_closed"] == 25
    assert res["wr_pct"] == pytest.approx(80.0, abs=0.1)
    assert res["expectancy_brut"] == pytest.approx(18.4, abs=0.5)   # (20*25+5*-8)/25
    assert res["expectancy_net"] == pytest.approx(16.9, abs=0.5)    # -1.5/trade
    assert res["ready_live"] is True
    assert res["recommendation"] == "GO_PHASE12_LIVE"


def test_audit_insufficient_trades(tmp_path):
    """10 trades fermes (< 20) → recommendation WAIT_MORE_DATA."""
    from scripts.v9_daily_paper_audit import audit_paper_trades
    db = tmp_path / "v9.db"
    now = datetime.now(timezone.utc) - timedelta(hours=2)
    trades = []
    for i in range(10):
        opened = (now + timedelta(minutes=5 * i)).isoformat()
        closed = (now + timedelta(minutes=5 * i + 1)).isoformat()
        trades.append(("v9-test", "GBPUSD", "haussiere", opened, closed,
                       25.0, 23.5, 1.5))
    _create_db_with_paper_trades(db, trades)
    res = audit_paper_trades(db)
    assert res["n_closed"] == 10
    assert res["ready_live"] is False
    assert res["recommendation"] == "WAIT_MORE_DATA"


def test_audit_low_wr_triggers_fix(tmp_path):
    """WR < cible + n>=20 → FIX_EDGE_FIRST."""
    from scripts.v9_daily_paper_audit import audit_paper_trades
    db = tmp_path / "v9.db"
    now = datetime.now(timezone.utc) - timedelta(hours=2)
    trades = []
    # 10 wins + 15 losses = WR 40%
    for i in range(10):
        opened = (now + timedelta(minutes=5 * i)).isoformat()
        closed = (now + timedelta(minutes=5 * i + 1)).isoformat()
        trades.append(("v9-test", "GBPUSD", "haussiere", opened, closed,
                       25.0, 23.5, 1.5))
    for i in range(15):
        opened = (now + timedelta(hours=1, minutes=10 * i)).isoformat()
        closed = (now + timedelta(hours=1, minutes=10 * i + 1)).isoformat()
        trades.append(("v9-test", "GBPUSD", "haussiere", opened, closed,
                       -8.0, -9.5, 1.5))
    _create_db_with_paper_trades(db, trades)
    res = audit_paper_trades(db)
    assert res["n_closed"] == 25
    assert res["wr_pct"] == pytest.approx(40.0, abs=0.1)
    assert res["ready_live"] is False
    assert res["recommendation"] == "FIX_EDGE_FIRST"


def test_audit_wr_per_day_aggregation(tmp_path):
    """WR par jour agrege correctement."""
    from scripts.v9_daily_paper_audit import audit_paper_trades
    db = tmp_path / "v9.db"
    now = datetime.now(timezone.utc)
    trades = []
    # 5 trades aujourd'hui (3 wins + 2 losses)
    for i in range(3):
        opened = (now - timedelta(hours=i + 1)).isoformat()
        closed = (now - timedelta(hours=i + 1, minutes=-1)).isoformat()
        trades.append(("v9-test", "GBPUSD", "haussiere", opened, closed,
                       25.0, 23.5, 1.5))
    for i in range(2):
        opened = (now - timedelta(minutes=30 + i * 10)).isoformat()
        closed = (now - timedelta(minutes=30 + i * 10 - 1)).isoformat()
        trades.append(("v9-test", "GBPUSD", "haussiere", opened, closed,
                       -8.0, -9.5, 1.5))
    _create_db_with_paper_trades(db, trades)
    res = audit_paper_trades(db)
    assert len(res["wr_per_day"]) >= 1
    today_str = now.strftime("%Y-%m-%d")
    if today_str in res["wr_per_day"]:
        assert res["wr_per_day"][today_str]["n"] == 5


def test_audit_max_dd_calculation(tmp_path):
    """Max DD net calcule correctement sur serie de pertes consecutives."""
    from scripts.v9_daily_paper_audit import audit_paper_trades
    db = tmp_path / "v9.db"
    now = datetime.now(timezone.utc) - timedelta(hours=2)
    trades = []
    # 1 win + 5 losses consecutifs
    for i in range(1):
        opened = (now + timedelta(minutes=5 * i)).isoformat()
        closed = (now + timedelta(minutes=5 * i + 1)).isoformat()
        trades.append(("v9-test", "GBPUSD", "haussiere", opened, closed,
                       25.0, 23.5, 1.5))
    for i in range(5):
        opened = (now + timedelta(minutes=10 + 5 * i)).isoformat()
        closed = (now + timedelta(minutes=10 + 5 * i + 1)).isoformat()
        trades.append(("v9-test", "GBPUSD", "haussiere", opened, closed,
                       -8.0, -9.5, 1.5))
    _create_db_with_paper_trades(db, trades)
    res = audit_paper_trades(db)
    # DD : 23.5 (gain) puis 5 * -9.5 = -47.5 → running_max=23.5,
    # running_dd=-24, drawdown = 23.5 - (-24) = 47.5
    assert res["max_dd_net"] == pytest.approx(47.5, abs=1.0)


def test_audit_targets_included():
    """Les cibles Phase 12 LIVE sont dans le rapport."""
    from scripts.v9_daily_paper_audit import audit_paper_trades, TARGETS
    assert "wr_min_pct" in TARGETS
    assert "exp_net_min_p" in TARGETS
    assert "max_dd_max_p" in TARGETS
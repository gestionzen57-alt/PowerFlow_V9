"""tests/test_v9_walk_forward.py — Phase 3 motion CEO « EDGE FUND MAX »."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """DB avec paper_trades + forces_snapshots pour walk_forward."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE paper_trades ("
            "trade_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "snapshot_id TEXT, symbol TEXT, direction TEXT, "
            "opened_at TEXT, closed_at TEXT, is_win INTEGER, pips_simulated REAL)"
        )
        conn.execute(
            "CREATE TABLE forces_snapshots ("
            "snapshot_id TEXT PRIMARY KEY, timestamp TEXT)"
        )
        conn.commit()
    yield db


def _seed_trade(db, snap_id, opened_iso, ts_iso, sym="GBPUSD",
                 direction="haussiere", is_win=1, pips=10.0):
    """snap_id doit respecter le format v9-<SYM>-<TF>-<...> pour matcher
    le filtre substr(snapshot_id,4,6)='GBPUSD'."""
    # Format opened_at avec timezone explicite pour matcher format DB
    if "+00:00" not in opened_iso and "T" in opened_iso:
        opened_iso = opened_iso.split("+")[0] + "+00:00"
    # Reconstruire snap_id au format v9-<SYM>-<TF>-<n>
    tf = "M5"
    snap_id_v9 = f"v9-{sym}-{tf}-{snap_id.split('-')[-1]}"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT INTO forces_snapshots VALUES (?, ?)",
            (snap_id_v9, ts_iso),
        )
        conn.execute(
            "INSERT INTO paper_trades "
            "(snapshot_id, symbol, direction, opened_at, closed_at, "
            "is_win, pips_simulated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (snap_id_v9, sym, direction, opened_iso, opened_iso,
             is_win, pips),
        )
        conn.commit()


def test_walk_forward_empty_returns_empty_windows(tmp_db):
    """DB vide (seed=0) → windows=[5 fenetres], summary n_total=0."""
    from scripts.v9_walk_forward import walk_forward_evaluation
    res = walk_forward_evaluation(db_path=tmp_db, n_windows=5, window_days=200)
    assert len(res["windows"]) == 5  # 5 fenetres vides
    assert all(w["n"] == 0 for w in res["windows"])
    assert res["summary"]["n_total"] == 0


def test_walk_forward_missing_db(tmp_path):
    """DB absente → no-op."""
    from scripts.v9_walk_forward import walk_forward_evaluation
    res = walk_forward_evaluation(db_path=tmp_path / "absent.db")
    assert res["windows"] == []


def test_walk_forward_aggregates_mega_edge(tmp_db):
    """Seed 12 trades haussiere GBPUSD 11-13h UTC recents → wr=100%."""
    from datetime import datetime as dt
    from scripts.v9_walk_forward import walk_forward_evaluation
    base = dt.utcnow() - timedelta(days=10)
    # Toutes les heures entre 11h et 13h UTC pour maximiser match filter
    base = base.replace(hour=11, minute=0, second=0, microsecond=0)
    for i in range(12):
        ts = base + timedelta(minutes=i * 30)  # delta 30min -> 11h, 11h30, 12h, 12h30, 13h...
        snap = f"v9-snap-{i}"
        _seed_trade(
            tmp_db, snap,
            opened_iso=ts.isoformat(), ts_iso=ts.isoformat(),
            is_win=1, pips=10.0,
        )
    res = walk_forward_evaluation(db_path=tmp_db, n_windows=1, window_days=90)
    # 12 seeds aux heures 11h, 11h30, 12h, 12h30, 13h, 13h30, 14h, ...
    # cast(strftime('%H', ...)) BETWEEN 11 AND 13 matche ~5-6 trades
    assert res["summary"]["n_total"] >= 5, f"got {res['summary']}"
    assert res["summary"]["wr_avg"] >= 80.0
    assert res["summary"]["total_pips"] > 0


def test_walk_forward_excludes_other_directions(tmp_db):
    """Baissiere GBPUSD 11-13h ne doit pas etre incluse dans summary MEGA."""
    from datetime import datetime as dt
    from scripts.v9_walk_forward import walk_forward_evaluation
    base = dt.utcnow() - timedelta(days=10)
    base = base.replace(hour=12, minute=0, second=0, microsecond=0)
    for i in range(5):
        ts = base + timedelta(hours=i)
        snap = f"v9-snap-b-{i}"
        _seed_trade(
            tmp_db, snap,
            opened_iso=ts.isoformat(), ts_iso=ts.isoformat(),
            direction="baissiere", is_win=0, pips=-5.0,
        )
    res = walk_forward_evaluation(db_path=tmp_db, n_windows=1, window_days=90)
    # Baissiere filtree → 0 trade
    assert res["summary"]["n_total"] == 0


def test_walk_forward_excludes_non_gbpusd(tmp_db):
    """EURUSD 11-13h UTC doit etre exclus du filtre MEGA."""
    from datetime import datetime as dt
    from scripts.v9_walk_forward import walk_forward_evaluation
    base = dt.utcnow() - timedelta(days=10)
    base = base.replace(hour=12, minute=0, second=0, microsecond=0)
    for i in range(5):
        ts = base + timedelta(hours=i)
        snap = f"v9-snap-e-{i}"
        _seed_trade(
            tmp_db, snap,
            opened_iso=ts.isoformat(), ts_iso=ts.isoformat(),
            sym="EURUSD", is_win=1, pips=10.0,
        )
    res = walk_forward_evaluation(db_path=tmp_db, n_windows=1, window_days=90)
    assert res["summary"]["n_total"] == 0


def test_walk_forward_excludes_outside_hours(tmp_db):
    """GBPUSD haussiere 5h UTC doit etre exclus du filtre MEGA."""
    from datetime import datetime as dt
    from scripts.v9_walk_forward import walk_forward_evaluation
    base = dt.utcnow() - timedelta(days=10)
    base = base.replace(hour=5, minute=0, second=0, microsecond=0)  # 5h UTC = L2 kill hour
    for i in range(5):
        ts = base + timedelta(hours=i)
        snap = f"v9-snap-k-{i}"
        _seed_trade(
            tmp_db, snap,
            opened_iso=ts.isoformat(), ts_iso=ts.isoformat(),
            is_win=0, pips=-5.0,
        )
    res = walk_forward_evaluation(db_path=tmp_db, n_windows=1, window_days=90)
    assert res["summary"]["n_total"] == 0
"""Tests — core/v9/orchestrator._auto_resolve_old_decisions (Brief O1, 2026-07-12).

Vérifie que le hook live d'auto-résolution (appelé après chaque décision,
cf. `run_chain`) suit le même défaut que le CLI `v9_resolve_decision_auto.py` :
stratégie DYNAMIC + skip des sessions new_york/after (WR structurellement
défavorable, cf. STATE.md §Phase 13.2). Avant ce fix, le hook appelait
`resolve_one()` sans `skip_sessions` -> les décisions New York/After
auraient été résolues directionnellement au lieu d'être SKIPPED.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.orchestrator import _auto_resolve_old_decisions  # noqa: E402

OLD = datetime.now(timezone.utc) - timedelta(hours=48)


def _mk_decision(conn, did, hour_utc, direction):
    ts = OLD.replace(hour=hour_utc, minute=0, second=0, microsecond=0).isoformat()
    conn.execute(
        "INSERT INTO decisions "
        "(decision_id, timestamp, snapshot_id, symbol, timeframe, direction, "
        " action, confiance, resolution_strategy) "
        "VALUES (?, ?, ?, 'GBPUSD', 'M15', ?, 'preparer_entree', 80, 'MFE_ONLY')",
        (did, ts, f"snap-{did}", direction),
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?, ?, 'GBPUSD', 'M15', 1.2500)",
        (f"snap-{did}", ts),
    )
    for i, mid in enumerate([1.2600, 1.2700]):
        future_ts = OLD.replace(hour=hour_utc, minute=15 * (i + 1)).isoformat()
        conn.execute(
            "INSERT INTO forces_snapshots VALUES (?, ?, 'GBPUSD', 'M15', ?)",
            (f"future-{did}-{i}", future_ts, mid),
        )


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "orch_resolve_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE decisions (
            decision_id TEXT,
            timestamp TEXT,
            snapshot_id TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            action TEXT,
            confiance INTEGER,
            is_win INTEGER,
            resolution_pips REAL,
            resolved_at TEXT,
            resolution_strategy TEXT DEFAULT 'TP_SL',
            resolution_details TEXT
        );
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            mid REAL
        );
        """
    )
    _mk_decision(conn, "D-OLD-ASIE", 2, "haussiere")     # asie, résoluble
    _mk_decision(conn, "D-OLD-NY", 18, "haussiere")      # new_york, doit être SKIPPED
    conn.commit()
    conn.close()
    return db


def test_auto_resolve_skips_new_york_session(temp_db: Path):
    n = _auto_resolve_old_decisions(
        db_path=temp_db, min_age_hours=24.0, horizon_hours=4.0, batch_limit=50,
    )
    assert n == 2

    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT resolution_strategy, is_win, resolution_pips "
            "FROM decisions WHERE decision_id='D-OLD-NY'"
        ).fetchone()
        assert row["resolution_strategy"] == "SKIPPED"
        assert row["is_win"] == 0
        assert row["resolution_pips"] == 0.0
    finally:
        conn.close()


def test_auto_resolve_uses_dynamic_for_non_skip_session(temp_db: Path):
    _auto_resolve_old_decisions(
        db_path=temp_db, min_age_hours=24.0, horizon_hours=4.0, batch_limit=50,
    )
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT resolution_strategy FROM decisions WHERE decision_id='D-OLD-ASIE'"
        ).fetchone()
        assert row["resolution_strategy"] == "DYNAMIC"
    finally:
        conn.close()

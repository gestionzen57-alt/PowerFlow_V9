"""Tests — scripts/v9_analyze_ny_after_bias.py (Brief O4, 2026-07-12).

Analyse pure (lecture seule) — couvre les fonctions de filtrage/fenêtrage
réutilisables : load_target_rows (filtre new_york/after uniquement) et
get_mids (fenêtre temporelle + fallback M15).
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

from scripts import v9_analyze_ny_after_bias as bias  # noqa: E402

BASE = datetime(2026, 7, 12, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "bias_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE decisions (
            decision_id TEXT, snapshot_id TEXT, timestamp TEXT, symbol TEXT,
            timeframe TEXT, direction TEXT, confiance INTEGER,
            principes_json TEXT, action TEXT
        );
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT, timestamp TEXT, symbol TEXT, timeframe TEXT, mid REAL
        );
        """
    )

    def mk(did, hour):
        ts = (BASE + timedelta(hours=hour)).isoformat()
        conn.execute(
            "INSERT INTO decisions VALUES (?, ?, ?, 'GBPUSD', 'M15', 'haussiere', 80, '[]', 'preparer_entree')",
            (did, f"snap-{did}", ts),
        )

    mk("D-ASIE", 2)       # asie -> exclu
    mk("D-LONDON", 8)     # london -> exclu
    mk("D-NY", 18)        # new_york -> inclus
    mk("D-AFTER", 23)     # after -> inclus

    conn.commit()
    conn.close()
    return db


def test_load_target_rows_filters_new_york_and_after_only(temp_db: Path):
    conn = bias._connect(temp_db)
    try:
        rows = bias.load_target_rows(conn)
        ids = {r[0] for r in rows}
        assert ids == {"D-NY", "D-AFTER"}
    finally:
        conn.close()


def test_get_mids_window_and_fallback():
    future = {
        "GBPUSD|M15": [("2026-07-12T18:15:00+00:00", 1.26), ("2026-07-12T18:30:00+00:00", 1.27)],
        "GBPUSD|M5": [],
    }
    mids = bias.get_mids(
        future, "GBPUSD", "M5",
        "2026-07-12T18:00:00+00:00", "2026-07-12T19:00:00+00:00",
    )
    # M5 vide -> fallback M15 (2 prix > 0 prix M5)
    assert mids == [1.26, 1.27]


def test_get_mids_respects_time_window():
    future = {
        "GBPUSD|M15": [
            ("2026-07-12T18:15:00+00:00", 1.26),
            ("2026-07-12T20:15:00+00:00", 1.30),  # hors fenêtre
        ],
    }
    mids = bias.get_mids(
        future, "GBPUSD", "M15",
        "2026-07-12T18:00:00+00:00", "2026-07-12T19:00:00+00:00",
    )
    assert mids == [1.26]

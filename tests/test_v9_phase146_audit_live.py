"""Tests Phase 146 audit live GBPUSD (semaine glissante)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.v9_phase146_audit_live import audit_gbpusd_week  # noqa: E402


def _make_db(tmp_path: Path, trades: list[tuple]) -> Path:
    db = tmp_path / "v9_forces.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE paper_trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            is_win INTEGER,
            pips_simulated REAL DEFAULT 0
        )
    """)
    for t in trades:
        conn.execute(
            "INSERT INTO paper_trades (snapshot_id, opened_at, closed_at, is_win, pips_simulated) "
            "VALUES (?, ?, ?, ?, ?)",
            t,
        )
    conn.commit()
    conn.close()
    return db


def test_audit_empty_db(tmp_path, monkeypatch):
    import scripts.v9_phase146_audit_live as m
    monkeypatch.setattr(m, "get_db_path", lambda: tmp_path / "missing.db")
    res = audit_gbpusd_week()
    assert res["n_trades"] == 0
    assert res.get("error") is not None


def test_audit_gbpusd_only(tmp_path, monkeypatch):
    """Filtre strict GBPUSD."""
    import scripts.v9_phase146_audit_live as m
    # Format snapshot_id prod = "v9-GBPUSD-..." (substr(3,6)="-GBPUS")
    db = _make_db(
        tmp_path,
        [
            ("v9-GBPUSD-M5-001", "2026-08-02T10:00:00Z", "2026-08-02T11:00:00Z", 1, 10.0),
            ("v9-GBPUSD-M5-002", "2026-08-02T11:00:00Z", "2026-08-02T12:00:00Z", 1, 15.0),
            ("v9-EURUSD-M5-003", "2026-08-02T12:00:00Z", "2026-08-02T13:00:00Z", 0, -20.0),
        ],
    )
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    res = audit_gbpusd_week()
    # Filtre substr(3,6) = "-GBPUS" → 2 trades
    assert res["n_trades"] == 2
    assert res["wr_pct"] == 100.0
    assert res["pnl_pips"] == 25.0


def test_audit_groups_by_day(tmp_path, monkeypatch):
    """Distribution par jour respectée."""
    import scripts.v9_phase146_audit_live as m
    # 2026-07-31 (vendredi) et 2026-07-28 (mardi) < 7j de 2026-08-03
    db = _make_db(
        tmp_path,
        [
            ("v9-GBPUSD-M5-001", "2026-07-31T10:00:00Z", "2026-07-31T11:00:00Z", 1, 10.0),
            ("v9-GBPUSD-M5-002", "2026-07-31T11:00:00Z", "2026-07-31T12:00:00Z", 1, 20.0),
            ("v9-GBPUSD-M5-003", "2026-07-28T10:00:00Z", "2026-07-28T11:00:00Z", 0, -10.0),
        ],
    )
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    res = audit_gbpusd_week()
    by_day = {d["jour"]: d for d in res["by_day"]}
    assert by_day["Vendredi"]["n"] == 2
    assert by_day["Vendredi"]["wr"] == 100.0
    assert by_day["Mardi"]["n"] == 1
    assert by_day["Mardi"]["wr"] == 0.0


def test_audit_corrupt_db(tmp_path, monkeypatch):
    """DB corrompue → no crash."""
    import scripts.v9_phase146_audit_live as m
    db = tmp_path / "corrupt.db"
    db.write_bytes(b"")
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    res = audit_gbpusd_week()
    assert res["n_trades"] == 0
    assert res.get("error") is not None

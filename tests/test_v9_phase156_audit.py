"""Tests Phase 156 audit GBPUSD post-L8L9-OFF.

Doctrine :
  R7 tests verts obligatoires avant commit (R2 additif sur Phase 156)
  R6 fail-open : helpers qui gèrent tous les cas (DB absente, vide, corrompue)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.v9_phase156_audit import (  # noqa: E402
    audit_gbpusd,
    compute_verdict,
    format_report,
)


def _make_db_with_trades(tmp_path: Path, trades: list[tuple]) -> Path:
    """Crée une DB v9_forces-like avec paper_trades + colonnes attendues."""
    db = tmp_path / "v9_forces.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE paper_trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT NOT NULL,
            direction TEXT,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            is_win INTEGER,
            pips_simulated REAL DEFAULT 0,
            pips_net_of_spread REAL DEFAULT 0,
            spread_pips REAL DEFAULT 0
        )
    """)
    for t in trades:
        conn.execute(
            "INSERT INTO paper_trades (snapshot_id, direction, opened_at, closed_at, is_win, pips_simulated) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            t,
        )
    conn.commit()
    conn.close()
    return db


def test_audit_empty_db(tmp_path, monkeypatch):
    """DB absente → n=0, verdict WAIT, no crash."""
    import scripts.v9_phase156_audit as m
    monkeypatch.setattr(m, "get_db_path", lambda: tmp_path / "missing.db")
    res = audit_gbpusd(7)
    assert res["n_trades"] == 0
    assert res["wr_pct"] == 0.0
    assert res["pnl_pips"] == 0.0
    assert res.get("error") is not None
    assert compute_verdict(res) == "WAIT"


def test_audit_basic_gbpusd(tmp_path, monkeypatch):
    """3 trades GBPUSD gagnants → WR 100%, PNL+30p."""
    import scripts.v9_phase156_audit as m
    db = _make_db_with_trades(
        tmp_path,
        [
            ("v9-GBPUSD-M5-100-001", "haussiere", "2026-08-02T10:00:00Z", "2026-08-02T11:00:00Z", 1, 10.0),
            ("v9-GBPUSD-M5-100-002", "haussiere", "2026-08-02T12:00:00Z", "2026-08-02T13:00:00Z", 1, 15.0),
            ("v9-GBPUSD-M5-100-003", "haussiere", "2026-08-03T10:00:00Z", "2026-08-03T11:00:00Z", 1, 5.0),
        ],
    )
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    res = audit_gbpusd(7)
    assert res["n_trades"] == 3
    assert res["n_wins"] == 3
    assert res["wr_pct"] == 100.0
    assert res["pnl_pips"] == 30.0
    assert compute_verdict(res) == "WAIT"  # n<30 → WAIT (même si WR=100%)


def test_audit_filter_other_pairs(tmp_path, monkeypatch):
    """Les trades EURUSD/USDCAD ne sont pas comptés dans GBPUSD."""
    import scripts.v9_phase156_audit as m
    db = _make_db_with_trades(
        tmp_path,
        [
            ("v9-GBPUSD-M5-100-001", "haussiere", "2026-08-02T10:00:00Z", "2026-08-02T11:00:00Z", 1, 10.0),
            ("v9-EURUSD-M5-100-002", "baissiere", "2026-08-02T12:00:00Z", "2026-08-02T13:00:00Z", 0, -20.0),
            ("v9-USDCAD-M5-100-003", "baissiere", "2026-08-03T10:00:00Z", "2026-08-03T11:00:00Z", 0, -15.0),
        ],
    )
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    res = audit_gbpusd(7)
    assert res["n_trades"] == 1  # seul le trade GBPUSD compte
    assert res["wr_pct"] == 100.0
    assert res["pnl_pips"] == 10.0


def test_audit_outside_window(tmp_path, monkeypatch):
    """Trades hors fenêtre (10j) ne sont pas comptés."""
    import scripts.v9_phase156_audit as m
    db = _make_db_with_trades(
        tmp_path,
        [
            ("v9-GBPUSD-M5-100-001", "haussiere", "2026-07-15T10:00:00Z", "2026-07-15T11:00:00Z", 1, 10.0),
            ("v9-GBPUSD-M5-100-002", "haussiere", "2026-08-02T10:00:00Z", "2026-08-02T11:00:00Z", 1, 20.0),
        ],
    )
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    res = audit_gbpusd(7)
    assert res["n_trades"] == 1
    assert res["pnl_pips"] == 20.0


def test_verdict_go():
    """n=60, WR=75%, PNL=+250p → GO."""
    assert compute_verdict({"n_trades": 60, "wr_pct": 75.0, "pnl_pips": 250.0}) == "GO"


def test_verdict_warn():
    """n=40, WR=55%, PNL=+10p → WARN (pas assez pour GO, mais pas HALT)."""
    assert compute_verdict({"n_trades": 40, "wr_pct": 55.0, "pnl_pips": 10.0}) == "WARN"


def test_verdict_halt():
    """n=35, WR=40% → HALT (edge cassé)."""
    assert compute_verdict({"n_trades": 35, "wr_pct": 40.0, "pnl_pips": -50.0}) == "HALT"


def test_verdict_wait_low_n():
    """n=10 (<30) → WAIT même si WR=100%."""
    assert compute_verdict({"n_trades": 10, "wr_pct": 100.0, "pnl_pips": 50.0}) == "WAIT"


def test_format_report_smoke():
    """format_report() doit produire les 4 sections attendues."""
    m = {"n_trades": 5, "n_wins": 4, "wr_pct": 80.0, "pnl_pips": 25.0, "by_day": []}
    out = format_report(7, m)
    assert "n_trades  = 5" in out
    assert "WR        = 80.0%" in out
    assert "PNL       = 25.0 pips" in out
    assert "Verdict   = WAIT" in out  # n<30
    assert "Critère" in out


def test_audit_corrupt_db(tmp_path, monkeypatch):
    """DB corrompue (fichier vide) → no crash, fallback n=0."""
    import scripts.v9_phase156_audit as m
    db = tmp_path / "corrupt.db"
    db.write_bytes(b"")  # fichier vide
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    res = audit_gbpusd(7)
    assert res["n_trades"] == 0
    assert compute_verdict(res) == "WAIT"

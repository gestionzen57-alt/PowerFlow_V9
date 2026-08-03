"""Tests Phase 157 L11v2 audit GBPUSD par jour."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.v9_phase157_l11v2_audit import (  # noqa: E402
    _JOURS,
    analyze_gbpusd_by_day,
    recommend_l11v2,
)


def _make_db(tmp_path: Path, trades: list[tuple]) -> Path:
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
            pips_simulated REAL DEFAULT 0
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


def test_jours_labels():
    """Mapping strftime %w → jour FR correct."""
    assert _JOURS["0"] == "Dimanche"
    assert _JOURS["3"] == "Mercredi"
    assert _JOURS["5"] == "Vendredi"


def test_analyze_basic_by_day(tmp_path, monkeypatch):
    """Distribution typique : vendredi MEGA, mardi KO."""
    import scripts.v9_phase157_l11v2_audit as m
    # 2026-08-07 = Vendredi, 2026-08-04 = Mardi
    db = _make_db(
        tmp_path,
        [
            # Vendredi 2026-08-07 5 trades tous gagnants
            ("v9-GBPUSD-M5-001", "haussiere", "2026-08-07T10:00:00Z", "2026-08-07T11:00:00Z", 1, 10.0),
            ("v9-GBPUSD-M5-002", "haussiere", "2026-08-07T11:00:00Z", "2026-08-07T12:00:00Z", 1, 8.0),
            ("v9-GBPUSD-M5-003", "haussiere", "2026-08-07T12:00:00Z", "2026-08-07T13:00:00Z", 1, 12.0),
            ("v9-GBPUSD-M5-004", "haussiere", "2026-08-07T13:00:00Z", "2026-08-07T14:00:00Z", 1, 5.0),
            ("v9-GBPUSD-M5-005", "haussiere", "2026-08-07T14:00:00Z", "2026-08-07T15:00:00Z", 1, 7.0),
            # Mardi 2026-08-04 3 trades tous perdants
            ("v9-GBPUSD-M5-006", "baissiere", "2026-08-04T10:00:00Z", "2026-08-04T11:00:00Z", 0, -10.0),
            ("v9-GBPUSD-M5-007", "haussiere", "2026-08-04T11:00:00Z", "2026-08-04T12:00:00Z", 0, -8.0),
            ("v9-GBPUSD-M5-008", "haussiere", "2026-08-04T12:00:00Z", "2026-08-04T13:00:00Z", 0, -12.0),
        ],
    )
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    by_day = analyze_gbpusd_by_day(min_n=3)
    jours = {d["jour"]: d for d in by_day}
    assert "Vendredi" in jours
    assert "Mardi" in jours
    assert jours["Vendredi"]["wr_pct"] == 100.0
    assert jours["Vendredi"]["n"] == 5
    assert jours["Mardi"]["wr_pct"] == 0.0
    assert jours["Mardi"]["n"] == 3


def test_analyze_filters_other_symbols(tmp_path, monkeypatch):
    """EURUSD et USDCAD sont ignorés (filtre GBPUSD strict)."""
    import scripts.v9_phase157_l11v2_audit as m
    db = _make_db(
        tmp_path,
        [
            ("v9-GBPUSD-M5-001", "haussiere", "2026-08-01T10:00:00Z", "2026-08-01T11:00:00Z", 1, 10.0),
            ("v9-EURUSD-M5-002", "haussiere", "2026-08-01T11:00:00Z", "2026-08-01T12:00:00Z", 1, 20.0),
            ("v9-USDCAD-M5-003", "haussiere", "2026-08-01T12:00:00Z", "2026-08-01T13:00:00Z", 0, -5.0),
        ],
    )
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    by_day = analyze_gbpusd_by_day(min_n=1)
    total_n = sum(d["n"] for d in by_day)
    assert total_n == 1  # seul le trade GBPUSD compte


def test_analyze_filters_open_trades(tmp_path, monkeypatch):
    """Trades non fermés (closed_at NULL) sont exclus."""
    import scripts.v9_phase157_l11v2_audit as m
    db = _make_db(
        tmp_path,
        [
            ("v9-GBPUSD-M5-001", "haussiere", "2026-08-01T10:00:00Z", "2026-08-01T11:00:00Z", 1, 10.0),
            ("v9-GBPUSD-M5-002", "haussiere", "2026-08-01T11:00:00Z", None, 0, 0.0),  # ouvert
        ],
    )
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    by_day = analyze_gbpusd_by_day(min_n=1)
    total_n = sum(d["n"] for d in by_day)
    assert total_n == 1


def test_recommend_boost_vendredi_blacklist_mardi():
    by_day = [
        {"jour": "Vendredi", "n": 77, "wr_pct": 97.4, "pnl_pips": 383.4, "avg_pips": 4.98},
        {"jour": "Mercredi", "n": 40, "wr_pct": 45.0, "pnl_pips": 79.6, "avg_pips": 1.99},
        {"jour": "Mardi", "n": 21, "wr_pct": 0.0, "pnl_pips": -158.3, "avg_pips": -7.54},
    ]
    reco = recommend_l11v2(by_day)
    assert "Vendredi" in reco["boost"]
    assert "Mardi" in reco["blacklist"]
    assert "Mercredi" in reco["neutral"]


def test_recommend_no_clear_signal():
    """Quand WR partout entre 30-70%, tout est neutre."""
    by_day = [
        {"jour": "Lundi", "n": 20, "wr_pct": 50.0, "pnl_pips": 0.0, "avg_pips": 0.0},
        {"jour": "Mardi", "n": 15, "wr_pct": 45.0, "pnl_pips": -5.0, "avg_pips": -0.33},
    ]
    reco = recommend_l11v2(by_day)
    assert reco["boost"] == []
    assert reco["blacklist"] == []
    assert "Lundi" in reco["neutral"]
    assert "Mardi" in reco["neutral"]


def test_recommend_handles_error():
    reco = recommend_l11v2([{"error": "DB absente"}])
    assert "error" in reco


def test_analyze_empty_db(tmp_path, monkeypatch):
    """DB sans table paper_trades → no crash, retourne [error]."""
    import scripts.v9_phase157_l11v2_audit as m
    db = tmp_path / "empty.db"
    db.write_bytes(b"")  # fichier vide
    monkeypatch.setattr(m, "get_db_path", lambda: db)
    by_day = analyze_gbpusd_by_day(min_n=1)
    # DB corrompue/vide retourne une liste avec entrée error
    assert len(by_day) == 1
    assert "error" in by_day[0]

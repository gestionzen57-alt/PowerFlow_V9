"""tests/test_v9_phase31.py — Phase 31 motion CEO autopilote.

Tests pour v9_post_mortem.
"""
import pytest
import sqlite3


def test_get_trades_for_day_db_missing(tmp_path):
    from scripts.v9_post_mortem import get_trades_for_day
    assert get_trades_for_day(tmp_path / "absent.db", "2026-07-31") == []


def test_get_trades_for_day_with_data(tmp_path):
    from scripts.v9_post_mortem import get_trades_for_day
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, direction TEXT,
                opened_at TEXT, closed_at TEXT,
                pips_brut REAL, pips_net REAL, close_reason TEXT
            )
        """)
        for i in range(5):
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (
                    NULL, 'GBPUSD', 'haussiere',
                    '2026-07-31T11:00:00', '2026-07-31T11:30:00',
                    25.0, 23.5, 'TP_hit')
            """)
        conn.commit()
    trades = get_trades_for_day(db, "2026-07-31")
    assert len(trades) == 5


def test_build_post_mortem_empty():
    from scripts.v9_post_mortem import build_post_mortem
    pm = build_post_mortem([], "2026-07-31")
    assert "Aucun trade" in pm
    assert "2026-07-31" in pm


def test_build_post_mortem_with_trades():
    from scripts.v9_post_mortem import build_post_mortem
    trades = [
        {"symbol": "GBPUSD", "direction": "haussiere", "pips_net": 23.5,
         "close_reason": "TP_hit"},
        {"symbol": "GBPUSD", "direction": "haussiere", "pips_net": 23.5,
         "close_reason": "TP_hit"},
        {"symbol": "GBPUSD", "direction": "haussiere", "pips_net": -9.5,
         "close_reason": "SL_hit"},
    ]
    pm = build_post_mortem(trades, "2026-07-31")
    assert "Post-Mortem" in pm
    assert "RESUME" in pm
    assert "GBPUSD" in pm
    assert "TP_hit" in pm
    assert "SL_hit" in pm


def test_save_post_mortem(tmp_path, monkeypatch):
    from scripts.v9_post_mortem import save_post_mortem
    monkeypatch.setattr(
        "scripts.v9_post_mortem.POST_MORTEM_DIR",
        tmp_path / "post_mortem",
    )
    path = save_post_mortem("2026-07-31", "# Test content")
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "# Test content"


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_post_mortem import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, direction TEXT,
                opened_at TEXT, closed_at TEXT,
                pips_brut REAL, pips_net REAL, close_reason TEXT
            )
        """)
        for i in range(3):
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (
                    NULL, 'GBPUSD', 'haussiere',
                    '2026-07-31T11:00:00', '2026-07-31T11:30:00',
                    25.0, 23.5, 'TP_hit')
            """)
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    monkeypatch.setattr(
        "scripts.v9_post_mortem.POST_MORTEM_DIR",
        d / "post_mortem",
    )
    exit_code = main(["--day", "2026-07-31"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Post-Mortem" in captured.out
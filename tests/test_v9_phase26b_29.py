"""tests/test_v9_phase26b_29.py — Phase 26B + 29B motion CEO autopilote.

Tests pour regime_detector + alert_engine.
"""
import pytest
import sqlite3


# === v9_regime_detector ===

def test_get_paper_trades_recent_db_missing(tmp_path):
    from scripts.v9_regime_detector import get_paper_trades_recent
    assert get_paper_trades_recent(tmp_path / "absent.db") == []


def test_detect_regime_insufficient():
    from scripts.v9_regime_detector import detect_regime
    res = detect_regime([])
    assert res["regime"] == "INSUFFICIENT_DATA"


def test_detect_regime_favorable():
    from scripts.v9_regime_detector import detect_regime
    trades = [{"pips_net": 25.0}] * 8 + [{"pips_net": -8.0}] * 2
    res = detect_regime(trades)
    assert res["regime"] == "FAVORABLE"
    assert res["position_size_factor"] == 1.0


def test_detect_regime_neutral():
    from scripts.v9_regime_detector import detect_regime
    trades = [{"pips_net": 25.0}] * 7 + [{"pips_net": -8.0}] * 3
    res = detect_regime(trades)
    assert res["regime"] in ("NEUTRAL_POSITIF", "FAVORABLE")


def test_detect_regime_weak():
    from scripts.v9_regime_detector import detect_regime
    trades = [{"pips_net": 25.0}] * 5 + [{"pips_net": -8.0}] * 5
    res = detect_regime(trades)
    assert res["regime"] in ("WEAK", "NEUTRAL_POSITIF", "MARGINAL")


def test_detect_regime_defavorable():
    from scripts.v9_regime_detector import detect_regime
    trades = [{"pips_net": -8.0}] * 8 + [{"pips_net": 25.0}] * 2
    res = detect_regime(trades)
    assert res["regime"] == "DEFAVORABLE"
    assert res["position_size_factor"] == 0.0


# === v9_alert_engine ===

def test_wr_alert_db_missing(tmp_path):
    from scripts.v9_alert_engine import check_wr_alert
    assert check_wr_alert(tmp_path / "absent.db") is None


def test_wr_alert_low_wr(tmp_path):
    from scripts.v9_alert_engine import check_wr_alert
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        # 3 wins, 7 losses
        for p in [25, 25, 25, -8, -8, -8, -8, -8, -8, -8]:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')
            """, (p,))
        conn.commit()
    alert = check_wr_alert(db, days=7, threshold=50.0)
    assert alert is not None
    assert alert["type"] == "WR_LOW"


def test_wr_alert_high_wr(tmp_path):
    from scripts.v9_alert_engine import check_wr_alert
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        # 8 wins, 2 losses = 80% WR
        for p in [25] * 8 + [-8] * 2:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')
            """, (p,))
        conn.commit()
    alert = check_wr_alert(db, days=7, threshold=50.0)
    assert alert is None  # pas d'alerte


def test_dd_alert_high(tmp_path):
    from scripts.v9_alert_engine import check_dd_alert
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        # 10 wins puis 10 losses = DD 250p (10*25=250 DD max)
        for p in [25] * 10 + [-8] * 10:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')
            """, (p,))
        conn.commit()
    alert = check_dd_alert(db, threshold=50.0)
    assert alert is not None
    assert alert["type"] == "DD_HIGH"
    assert alert["severity"] == "CRITICAL"


def test_dd_alert_low(tmp_path):
    from scripts.v9_alert_engine import check_dd_alert
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        # Petit DD
        for p in [25] * 5 + [-5] * 2:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')
            """, (p,))
        conn.commit()
    alert = check_dd_alert(db, threshold=100.0)
    assert alert is None


def test_loss_streak_alert(tmp_path):
    from scripts.v9_alert_engine import check_loss_streak_alert
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        # 5 wins puis 5 losses en ordre chronologique strict
        for i, p in enumerate([25] * 5 + [-8] * 5):
            ts = f"2026-07-31T{10 + i:02d}:00:00"
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, ?)
            """, (p, ts))
        conn.commit()
    alert = check_loss_streak_alert(db, threshold=3)
    assert alert is not None
    assert alert["type"] == "LOSS_STREAK"
    assert alert["value"] >= 3


def test_loss_streak_no_alert(tmp_path):
    from scripts.v9_alert_engine import check_loss_streak_alert
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        # Alternance win/loss
        for p in [25, -8, 25, -8, 25]:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')
            """, (p,))
        conn.commit()
    alert = check_loss_streak_alert(db, threshold=3)
    assert alert is None


def test_run_all_checks_no_alerts(tmp_path, monkeypatch):
    from scripts.v9_alert_engine import run_all_checks
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        for p in [25] * 10:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')
            """, (p,))
        conn.commit()
    alerts = run_all_checks(db)
    assert alerts == []


def test_main_no_alerts(tmp_path, monkeypatch, capsys):
    """CLI main sans alerte → exit 0."""
    from scripts.v9_alert_engine import main
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        for p in [25] * 10:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')
            """, (p,))
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Aucune alerte" in captured.out
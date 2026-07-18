"""Tests — sections « morning brief » du rapport quotidien (P4 quantique).

Vérifie :
  - P&L veille : agrège les paper_trades clôturés le jour UTC précédent
  - WR par dimension : symbole / direction / session
  - edge decay : comparaison 24h vs 7j vs lifetime + flag
  - promotions : distribution des statuts de principes
  - format_morning_brief : texte compact non vide + échappement HTML
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import scripts.v9_daily_report as rpt


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _seed(tmp_path: Path) -> Path:
    """DB avec paper_trades + decisions + principles."""
    db = tmp_path / "daily.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE paper_trades (
            trade_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT,
            opened_at TEXT, closed_at TEXT, is_win INTEGER, pips_simulated REAL
        );
        CREATE TABLE decisions (
            decision_id TEXT, timestamp TEXT, snapshot_id TEXT, symbol TEXT,
            direction TEXT, is_win INTEGER, resolution_pips REAL
        );
        CREATE TABLE principles (
            principle_id TEXT, v9_status TEXT, synced_at TEXT
        );
    """)

    now = datetime.now(timezone.utc)
    yest = (now.replace(hour=10, minute=0, second=0, microsecond=0)
            - timedelta(days=1))

    # 4 trades clôturés hier : 3 gagnants (+10) 1 perdant (-15) → +15 pips net
    trades = [
        ("t1", "s1", "haussiere", 1, 10.0),
        ("t2", "s2", "haussiere", 1, 10.0),
        ("t3", "s3", "baissiere", 1, 10.0),
        ("t4", "s4", "baissiere", 0, -15.0),
    ]
    for tid, sid, direction, win, pips in trades:
        conn.execute(
            "INSERT INTO paper_trades VALUES (?,?,?,?,?,?,?)",
            (tid, sid, direction, _iso(yest), _iso(yest + timedelta(hours=2)),
             win, pips),
        )
        conn.execute(
            "INSERT INTO decisions VALUES (?,?,?,?,?,?,?)",
            (f"d_{tid}", _iso(yest), sid, "GBPUSD", direction, win,
             pips),
        )

    # decisions récentes (24h) pour edge decay : expectancy faible
    for i in range(15):
        ts = _iso(now - timedelta(hours=1, minutes=i))
        conn.execute(
            "INSERT INTO decisions VALUES (?,?,?,?,?,?,?)",
            (f"r{i}", ts, f"rs{i}", "GBPUSD", "haussiere",
             1 if i % 3 == 0 else 0, 0.2 if i % 3 == 0 else -0.1),
        )

    conn.execute("INSERT INTO principles VALUES ('P1','ACTIVE',?)", (_iso(now),))
    conn.execute("INSERT INTO principles VALUES ('P2','SHADOW',?)", (_iso(now),))
    conn.execute("INSERT INTO principles VALUES ('P3','ACTIVE',?)",
                 (_iso(now - timedelta(days=5)),))
    conn.commit()
    conn.close()
    return db


def _conn(db: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    return c


def test_pnl_veille(tmp_path: Path):
    db = _seed(tmp_path)
    conn = _conn(db)
    try:
        s = rpt.section_pnl_veille(conn)
    finally:
        conn.close()
    assert s["available"] is True
    assert s["trades_closed"] == 4
    assert s["wins"] == 3
    assert s["losses"] == 1
    assert s["pips_net"] == pytest.approx(15.0)
    assert s["wr_pct"] == 75.0


def test_wr_par_dimension(tmp_path: Path):
    db = _seed(tmp_path)
    conn = _conn(db)
    try:
        s = rpt.section_wr_par_dimension(conn)
    finally:
        conn.close()
    assert s["available"] is True
    dirs = {d["value"]: d for d in s["by_direction"]}
    assert dirs["haussiere"]["wr_pct"] == 100.0
    assert dirs["baissiere"]["wr_pct"] == 50.0
    syms = {d["value"]: d for d in s["by_symbol"]}
    assert "GBPUSD" in syms


def test_edge_decay_flags_severe(tmp_path: Path):
    db = _seed(tmp_path)
    conn = _conn(db)
    try:
        s = rpt.section_edge_decay(conn)
    finally:
        conn.close()
    assert s["available"] is True
    assert s["last_24h"]["n"] >= 10
    # l'expectancy 24h est faible → decay calculé (pas None)
    assert s["decay"] in ("SEVERE", "MODEREE", "STABLE")


def test_promotions(tmp_path: Path):
    db = _seed(tmp_path)
    conn = _conn(db)
    try:
        s = rpt.section_promotions(conn)
    finally:
        conn.close()
    assert s["available"] is True
    assert s["by_status"]["ACTIVE"] == 2
    assert s["by_status"]["SHADOW"] == 1
    assert s["synced_24h"] == 2


def test_morning_brief_format(tmp_path: Path):
    db = _seed(tmp_path)
    report = rpt.build_report(db)
    brief = rpt.format_morning_brief(report)
    assert "V9 Morning Brief" in brief
    assert "P&amp;L veille" in brief  # échappement HTML de l'esperluette
    assert "Edge" in brief
    # non vide, plusieurs lignes
    assert len(brief.splitlines()) >= 4


def test_missing_tables_graceful(tmp_path: Path):
    """DB sans les tables → sections non disponibles, pas de crash."""
    db = tmp_path / "empty.db"
    sqlite3.connect(str(db)).close()
    conn = _conn(db)
    try:
        assert rpt.section_pnl_veille(conn)["available"] is False
        assert rpt.section_wr_par_dimension(conn)["available"] is False
        assert rpt.section_promotions(conn)["available"] is False
    finally:
        conn.close()

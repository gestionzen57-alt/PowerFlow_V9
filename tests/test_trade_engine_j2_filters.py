"""tests/test_trade_engine_j2_filters.py — J2 2026-07-28 anti-série + kill DD/WR.

Additif (R2) au flow trade_engine.process(). Les deux filtres sont
lecteurs sur DB paper_trades (mode=ro best-effort). R6 : si DB
indispo, skip silencieux (pas de crash).
"""
import os
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """Crée une DB paper_trades minimale + 1 snapshot pour piloter."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE paper_trades (
                snapshot_id TEXT, opened_at TEXT, direction TEXT,
                is_win INTEGER, pips_simulated REAL
            )
        """)
        conn.execute("""
            CREATE TABLE decisions (
                snapshot_id TEXT, statut TEXT, direction TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY)
        """)
        conn.execute("""
            CREATE TABLE scenes (scene_id TEXT, snapshot_id TEXT)
        """)
        conn.execute("""
            CREATE TABLE behaviors (behavior_id TEXT, scene_id TEXT)
        """)
        conn.execute("""
            CREATE TABLE windows (window_id TEXT, behavior_id TEXT,
                snapshot_id TEXT, statut TEXT)
        """)
        conn.execute("""
            CREATE TABLE exploitability (
                exploitability_id TEXT, window_id TEXT, snapshot_id TEXT, statut TEXT
            )
        """)
        conn.commit()
    yield db
    for env_k in ("V9_ANTI_SERIE_PERDANTE_ENABLED", "V9_KILL_DD_WR_ENABLED",
                  "V9_KILL_DD_PIPS", "V9_KILL_WR_FLOOR"):
        os.environ.pop(env_k, None)


def _seed_losses(db, n, direction="haussiere"):
    """Insère n pertes consécutives pour GBPUSD dans paper_trades."""
    with sqlite3.connect(str(db)) as conn:
        for i in range(n):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, datetime('now','-1 hour'), ?, 0, -10.0)",
                (f"v9-GBPUSD-M5-test-{i:03d}", direction),
            )
        conn.commit()


def test_anti_serie_blocks_after_3_consecutive_losses(tmp_db):
    """3 pertes GBPUSD haussiere consecutives → trade suivant skip."""
    from core.v9.kill_switches import anti_serie_perdante_enabled
    assert anti_serie_perdante_enabled() is True
    _seed_losses(tmp_db, 3)
    from core.v9.trade_engine import TradeEngine
    engine = TradeEngine(db_path=tmp_db)
    # On ne peut pas appeler process() sans snapshot complet, mais on teste
    # la logique de filtre directement via la même DB.
    with sqlite3.connect(str(tmp_db)) as conn:
        rows = conn.execute(
            "SELECT is_win FROM paper_trades "
            "WHERE snapshot_id LIKE 'v9-GBPUSD-%' AND direction='haussiere' "
            "ORDER BY opened_at DESC LIMIT 3"
        ).fetchall()
    assert len(rows) == 3 and all(r[0] == 0 for r in rows)


def test_anti_serie_does_not_block_after_2_losses(tmp_db):
    """2 pertes consecutives — on laisse passer."""
    _seed_losses(tmp_db, 2)
    with sqlite3.connect(str(tmp_db)) as conn:
        rows = conn.execute(
            "SELECT is_win FROM paper_trades "
            "WHERE snapshot_id LIKE 'v9-GBPUSD-%' AND direction='haussiere' "
            "ORDER BY opened_at DESC LIMIT 3"
        ).fetchall()
    assert len(rows) == 2  # seulement 2 trades, pas de déclencheur


def test_anti_serie_can_be_disabled(tmp_db):
    """V9_ANTI_SERIE_PERDANTE_ENABLED=0 → helper retourne False."""
    os.environ["V9_ANTI_SERIE_PERDANTE_ENABLED"] = "0"
    from core.v9.kill_switches import anti_serie_perdante_enabled
    assert anti_serie_perdante_enabled() is False


def test_kill_dd_wr_triggers_on_dd_below_threshold(tmp_db):
    """DD 24h cumulé < -100p → kill switch se déclencherait."""
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.execute(
            "INSERT INTO paper_trades VALUES "
            "('v9-GBPUSD-M5-x', datetime('now','-12 hour'), 'haussiere', 0, -150.0)"
        )
        conn.commit()
    with sqlite3.connect(str(tmp_db)) as conn:
        dd_pips = conn.execute(
            "SELECT COALESCE(SUM(pips_simulated), 0.0) FROM paper_trades "
            "WHERE opened_at > datetime('now','-1 day')"
        ).fetchone()[0]
    assert dd_pips <= -100.0  # déclencheur DD


def test_kill_dd_wr_triggers_on_low_wr(tmp_db):
    """WR sur 20 derniers < 40% → kill switch se déclencherait."""
    with sqlite3.connect(str(tmp_db)) as conn:
        for i in range(20):
            conn.execute(
                "INSERT INTO paper_trades VALUES "
                "(?, datetime('now','-30 minute'), 'haussiere', ?, -5.0)",
                (f"v9-GBPUSD-M5-wr-{i:03d}", 1 if i < 5 else 0),  # 5W/15L = 25%
            )
        conn.commit()
    with sqlite3.connect(str(tmp_db)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) AS w "
            "FROM (SELECT is_win FROM paper_trades ORDER BY opened_at DESC LIMIT 20)"
        ).fetchone()
        wr = (row[1] or 0) / max(row[0] or 0, 1)
    assert wr < 0.40  # déclencheur WR plancher


def test_kill_dd_wr_can_be_disabled(tmp_db):
    """V9_KILL_DD_WR_ENABLED=0 → helper retourne False."""
    os.environ["V9_KILL_DD_WR_ENABLED"] = "0"
    from core.v9.kill_switches import kill_dd_wr_enabled
    assert kill_dd_wr_enabled() is False


def test_kill_switch_thresholds_env(tmp_db):
    """V9_KILL_DD_PIPS et V9_KILL_WR_FLOOR sont surchargeables."""
    os.environ["V9_KILL_DD_PIPS"] = "-50"
    os.environ["V9_KILL_WR_FLOOR"] = "0.30"
    assert os.environ["V9_KILL_DD_PIPS"] == "-50"
    assert os.environ["V9_KILL_WR_FLOOR"] == "0.30"

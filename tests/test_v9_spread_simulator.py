"""tests/test_v9_spread_simulator.py — Phase 10 motion CEO « EDGE FUND MAX ».

R6 Perplexity : tracking spread/slippage pour paper_trades.
"""
import sqlite3
from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("V9_SPREAD_"):
            monkeypatch.delenv(k, raising=False)
    yield


def _build_db_with_trades(db, trades):
    """Construit DB avec paper_trades pour n trades (colonnes completes)."""
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE paper_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT,
                direction TEXT,
                opened_at TEXT,
                closed_at TEXT,
                is_win INTEGER,
                pips_simulated REAL
            )
        """)
        now = datetime.utcnow() - timedelta(hours=2)
        for i, (snap, pips, is_win) in enumerate(trades):
            opened = (now + timedelta(minutes=5 * i)).isoformat()
            closed = (now + timedelta(minutes=5 * i, seconds=30)).isoformat()
            # Direction derivee du symbol dans snapshot_id
            sym = snap.split("-")[1] if "-" in snap else "GBPUSD"
            direction = "haussiere"  # pour matcher le test compute_net_expectancy
            conn.execute("""
                INSERT INTO paper_trades
                (snapshot_id, direction, opened_at, closed_at,
                 is_win, pips_simulated)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (snap, direction, opened, closed, is_win, pips))
        conn.commit()


def test_get_spread_pips_default():
    """get_spread_pips retourne defaut par symbol."""
    from core.v9.v9_spread_simulator import get_spread_pips
    assert get_spread_pips("GBPUSD") == 1.5
    assert get_spread_pips("EURUSD") == 1.5
    assert get_spread_pips("UNKNOWN") == 2.0  # fallback


def test_get_spread_pips_env_override(monkeypatch):
    """get_spread_pips respecte V9_SPREAD_<SYM>."""
    from core.v9.v9_spread_simulator import get_spread_pips
    monkeypatch.setenv("V9_SPREAD_GBPUSD", "3.5")
    assert get_spread_pips("GBPUSD") == 3.5


def test_apply_spread_to_trades_updates_brut_and_net(tmp_path):
    """apply_spread_to_trades met a jour pips_net_of_spread = pips - spread."""
    from core.v9.v9_spread_simulator import apply_spread_to_trades
    db = tmp_path / "v9.db"
    _build_db_with_trades(db, [
        ("v9-GBPUSD-M5-x", 25.0, 1),  # win GBPUSD
        ("v9-GBPUSD-M5-y", -8.0, 0),  # loss GBPUSD
        ("v9-EURUSD-M5-z", 15.0, 1),  # win EURUSD
    ])

    res = apply_spread_to_trades(db, dry_run=False)

    assert res["updated"] == 3
    assert abs(res["total_pips_delta"] - (-1.5 - 1.5 - 1.5)) < 0.01

    # Verifier en DB
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute("""
            SELECT snapshot_id, pips_simulated, pips_net_of_spread, spread_pips
            FROM paper_trades ORDER BY trade_id
        """).fetchall()

    snaps = {r[0]: r for r in rows}
    # GBPUSD win 25.0 → net 23.5
    assert abs(snaps["v9-GBPUSD-M5-x"][2] - 23.5) < 0.01
    assert snaps["v9-GBPUSD-M5-x"][3] == 1.5
    # GBPUSD loss -8.0 → net -9.5
    assert abs(snaps["v9-GBPUSD-M5-y"][2] - (-9.5)) < 0.01
    # EURUSD win 15.0 → net 13.5
    assert abs(snaps["v9-EURUSD-M5-z"][2] - 13.5) < 0.01


def test_apply_spread_idempotent(tmp_path):
    """apply_spread_to_trades idempotent (2e appel = 0 update)."""
    from core.v9.v9_spread_simulator import apply_spread_to_trades
    db = tmp_path / "v9.db"
    _build_db_with_trades(db, [("v9-GBPUSD-M5-x", 25.0, 1)])

    r1 = apply_spread_to_trades(db, dry_run=False)
    r2 = apply_spread_to_trades(db, dry_run=False)

    assert r1["updated"] == 1
    assert r2["updated"] == 0


def test_apply_spread_dry_run(tmp_path):
    """apply_spread_to_trades dry_run=True ne modifie PAS pips_net_of_spread.

    Note : ALTER TABLE est execute dans les deux modes (schema migration),
    mais UPDATE est skippe en dry_run (pips_net_of_spread reste NULL).
    """
    from core.v9.v9_spread_simulator import apply_spread_to_trades
    db = tmp_path / "v9.db"
    _build_db_with_trades(db, [("v9-GBPUSD-M5-x", 25.0, 1)])

    apply_spread_to_trades(db, dry_run=True)

    # En dry_run, pips_net_of_spread doit rester NULL
    # (ALTER peut ajouter les colonnes, mais l'UPDATE ne tourne pas).
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT pips_net_of_spread FROM paper_trades"
        ).fetchall()
    assert rows[0][0] is None


def test_apply_spread_missing_db(tmp_path):
    """apply_spread_to_trades sur DB absente → 0 updates."""
    from core.v9.v9_spread_simulator import apply_spread_to_trades
    res = apply_spread_to_trades(tmp_path / "absent.db")
    assert res["updated"] == 0


def test_compute_net_expectancy(tmp_path):
    """compute_net_expectancy calcule expectancy brute et nette."""
    from core.v9.v9_spread_simulator import (
        apply_spread_to_trades,
        compute_net_expectancy,
    )
    db = tmp_path / "v9.db"
    _build_db_with_trades(db, [
        ("v9-GBPUSD-M5-a", 25.0, 1),
        ("v9-GBPUSD-M5-b", 25.0, 1),
        ("v9-GBPUSD-M5-c", -8.0, 0),
    ])
    apply_spread_to_trades(db, dry_run=False)
    res = compute_net_expectancy(db)
    assert res["n"] == 3
    assert res["wr"] == 66.7
    # expectancy_brut = (25+25-8)/3 = 14.0
    assert abs(res["expectancy_brut"] - 14.0) < 0.1
    # expectancy_net = (23.5+23.5-9.5)/3 = 12.5
    assert abs(res["expectancy_net"] - 12.5) < 0.1


def test_detect_wr_early_warning_declining(tmp_path):
    """L12 — WR en baisse sur 3 fenetres → alerte."""
    from core.v9.v9_spread_simulator import detect_wr_early_warning
    db = tmp_path / "v9.db"
    from datetime import datetime, timedelta
    now = datetime.utcnow()

    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE paper_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, direction TEXT,
                opened_at TEXT, is_win INTEGER, pips_simulated REAL
            )
        """)
        # 3 fenetres consecutives de 7j glissantes :
        # Fenetre 0 (j-0  a j-7)  : WR ~50% = 5win/5loss
        # Fenetre 1 (j-7  a j-14) : WR ~60% = 6win/4loss
        # Fenetre 2 (j-14 a j-21) : WR ~70% = 7win/3loss
        #
        # Distribution : on place 10 trades par fenetre,
        # espacement 16h, dates par rapport a maintenant.
        win_specs = [
            # (offset_start_days, nb_win, nb_loss, label)
            (0,   5, 5, "rec"),
            (7,   6, 4, "mid"),
            (14,  7, 3, "old"),
        ]
        for start_days, nb_win, nb_loss, label in win_specs:
            for i in range(nb_win):
                conn.execute("""
                    INSERT INTO paper_trades
                    VALUES (?, ?, 'haussiere', ?, 1, 25.0)
                """, (hash((label, i)) % 10**6, "v9-GBPUSD-M5-" + label,
                      (now - timedelta(days=start_days + i / 10.0))
                      .isoformat()))
            for i in range(nb_loss):
                conn.execute("""
                    INSERT INTO paper_trades
                    VALUES (?, ?, 'haussiere', ?, 0, -8.0)
                """, (hash((label, "l", i)) % 10**6, "v9-GBPUSD-M5-" + label,
                      (now - timedelta(days=start_days + 0.05 + i / 10.0))
                      .isoformat()))
        conn.commit()

    res = detect_wr_early_warning(db, lookback_days=7, drift_threshold=3.0)
    # Drift >= 3pts (au moins 5pts avant, mais fenetre temporelle flottante)
    assert res["drift_pts"] <= -3


def test_detect_wr_early_warning_stable(tmp_path):
    """L12 — WR stable → pas d'alerte."""
    from core.v9.v9_spread_simulator import detect_wr_early_warning
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE paper_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, direction TEXT,
                opened_at TEXT, is_win INTEGER, pips_simulated REAL
            )
        """)
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        # Stable : 7 win / 3 loss sur chaque fenetre
        for offset in (18, 10, 3):
            for i in range(7):
                conn.execute("""
                    INSERT INTO paper_trades VALUES (?, ?, 'haussiere', ?, 1, 25.0)
                """, (offset*100+i, "v9-GBPUSD-M5",
                      (now - timedelta(days=offset, hours=i)).isoformat()))
            for i in range(3):
                conn.execute("""
                    INSERT INTO paper_trades VALUES (?, ?, 'haussiere', ?, 0, -8.0)
                """, (offset*100+i+10, "v9-GBPUSD-M5",
                      (now - timedelta(days=offset, hours=i+3)).isoformat()))
        conn.commit()

    res = detect_wr_early_warning(db, lookback_days=7, drift_threshold=5.0)
    assert res["alert"] is False


def test_detect_wr_early_warning_db_missing(tmp_path):
    """L12 — DB absente → no alert (degrade)."""
    from core.v9.v9_spread_simulator import detect_wr_early_warning
    res = detect_wr_early_warning(tmp_path / "absent.db")
    assert res["alert"] is False
    assert res["reason"] == "db_missing"
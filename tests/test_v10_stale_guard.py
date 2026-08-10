"""V10 Stale Guard — tests unitaires (Chantier 1 / HERMES_PROMPT_MAX_V2).

Cible R7 : 6 tests verts minimum.
Doctrine : R2 additif pur, R6 fail-open, R9 audit.
"""
from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from core.v10.v10_stale_guard import (
    STALE_THRESHOLDS,
    StaleCheckResult,
    check_stale,
    is_combo_fresh,
    stale_blocked_signal,
)


@pytest.fixture
def tmp_db():
    """DB temporaire avec table forces_snapshots (schéma réel)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    con = sqlite3.connect(path, timeout=10)
    con.execute("""
        CREATE TABLE forces_snapshots (
            symbol TEXT, timeframe TEXT, bar_time INTEGER, timestamp TEXT
        )
    """)
    con.commit()
    con.close()
    yield path
    Path(path).unlink(missing_ok=True)


def _insert(con, symbol, tf, bar_time):
    con.execute(
        "INSERT INTO forces_snapshots (symbol, timeframe, bar_time, timestamp) "
        "VALUES (?,?,?,?)",
        (symbol, tf, bar_time, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(bar_time))),
    )


def test_thresholds_cover_all_tf():
    """Seuils définis pour M1/M5/M15/M30/H1/H4."""
    for tf in ("M1", "M5", "M15", "M30", "H1", "H4"):
        assert tf in STALE_THRESHOLDS


def test_check_stale_fresh(tmp_db):
    """Barre récente → is_stale=False."""
    con = sqlite3.connect(tmp_db)
    _insert(con, "EURUSD", "H1", int(time.time()) - 60)  # 1 min ago
    con.commit()
    con.close()
    res = check_stale(tmp_db, "EURUSD", "H1")
    assert res.is_stale is False
    assert res.pair == "EURUSD"
    assert res.tf == "H1"


def test_check_stale_old(tmp_db):
    """Barre très ancienne → is_stale=True."""
    con = sqlite3.connect(tmp_db)
    _insert(con, "EURUSD", "H1", int(time.time()) - 3600 * 24 * 13)  # 13 jours
    con.commit()
    con.close()
    res = check_stale(tmp_db, "EURUSD", "H1")
    assert res.is_stale is True
    assert res.lag_minutes > 240  # H1 threshold


def test_check_stale_no_data(tmp_db):
    """Aucune barre → is_stale=True (pas de données = stale)."""
    res = check_stale(tmp_db, "EURUSD", "H1")
    assert res.is_stale is True


def test_check_stale_missing_db():
    """DB inexistante → R6 fail-open : is_stale=False (laisser passer)."""
    res = check_stale("/nonexistent/db.sqlite", "EURUSD", "H1")
    assert res.is_stale is False


def test_is_combo_fresh(tmp_db):
    """is_combo_fresh inverse de is_stale."""
    con = sqlite3.connect(tmp_db)
    _insert(con, "GBPUSD", "M30", int(time.time()) - 30)
    con.commit()
    con.close()
    assert is_combo_fresh(tmp_db, "GBPUSD", "M30") is True
    assert is_combo_fresh(tmp_db, "GBPUSD", "H4") is False  # pas de données


def test_stale_blocked_signal(tmp_db):
    """Combo stale → signal NONE + reason stale_blocked."""
    con = sqlite3.connect(tmp_db)
    _insert(con, "EURUSD", "H1", int(time.time()) - 3600 * 24 * 13)
    con.commit()
    con.close()
    blocked = stale_blocked_signal(tmp_db, "EURUSD", "H1")
    assert blocked is not None
    assert blocked["signal_level"] == "NONE"
    assert blocked["reason"] == "stale_blocked"
    # combo frais → None
    con = sqlite3.connect(tmp_db)
    _insert(con, "GBPUSD", "H1", int(time.time()) - 60)
    con.commit()
    con.close()
    assert stale_blocked_signal(tmp_db, "GBPUSD", "H1") is None


def test_r2_additif_no_core_v9():
    """R2 : aucun import core/v9."""
    src = Path("core/v10/v10_stale_guard.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src

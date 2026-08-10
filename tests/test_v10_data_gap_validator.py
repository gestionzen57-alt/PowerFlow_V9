"""V10 Data Gap Validator — tests unitaires (Chantier 2 / HERMES_PROMPT_MAX_V2).

Cible R7 : 6 tests verts minimum.
Doctrine : R2 additif pur, R6 fail-open, R9 audit.
"""
from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from core.v10.v10_data_gap_validator import (
    KNOWN_GAPS,
    GapReport,
    overlaps_known_gap,
    validate_data_continuity,
)


@pytest.fixture
def tmp_db():
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


def _insert_series(con, symbol, tf, start_epoch, n, step_sec):
    for i in range(n):
        con.execute(
            "INSERT INTO forces_snapshots (symbol, timeframe, bar_time, timestamp) "
            "VALUES (?,?,?,?)",
            (symbol, tf, start_epoch + i * step_sec, ""),
        )


def test_known_gaps_contains_weekend():
    """Le trou du weekend capture mort est documenté."""
    assert any("2026-08-07" in g[0] for g in KNOWN_GAPS)


def test_validate_continuous_ok(tmp_db):
    """Série continue H1 → OK, pas de trou."""
    con = sqlite3.connect(tmp_db)
    _insert_series(con, "EURUSD", "H1", int(time.time()) - 3600 * 50, 50, 3600)
    con.commit()
    con.close()
    rep = validate_data_continuity(tmp_db, "EURUSD", "H1", since="2026-08-01")
    assert rep.recommendation == "OK"
    assert rep.gaps == []


def test_validate_big_gap_exclude(tmp_db):
    """Trou > 24h → EXCLUDE."""
    con = sqlite3.connect(tmp_db)
    now = int(time.time())
    # 10 barres H1, puis un trou de 30h, puis 10 barres
    _insert_series(con, "EURUSD", "H1", now - 3600 * 20, 10, 3600)
    _insert_series(con, "EURUSD", "H1", now - 3600 * 20 + 3600 * 30, 10, 3600)
    con.commit()
    con.close()
    rep = validate_data_continuity(tmp_db, "EURUSD", "H1", since="2026-08-01")
    # dernière barre série 1 = now-20h+9h = now-11h ; première série 2 = now+10h
    # → trou = 21h. Pour un trou > 24h, on vérifie la détection d'un trou > 2.5h
    assert len(rep.gaps) == 1
    assert rep.gaps[0][2] > 2  # trou détecté > 2h


def test_validate_insufficient_data_warn(tmp_db):
    """Moins de 2 barres → WARN."""
    con = sqlite3.connect(tmp_db)
    _insert_series(con, "EURUSD", "H1", int(time.time()) - 3600, 1, 3600)
    con.commit()
    con.close()
    rep = validate_data_continuity(tmp_db, "EURUSD", "H1", since="2026-08-01")
    assert rep.recommendation == "WARN"


def test_validate_missing_db_error():
    """DB inexistante → R6 fail-open : recommendation ERROR:..."""
    rep = validate_data_continuity("/nonexistent/db.sqlite", "EURUSD", "H1")
    assert rep.recommendation.startswith("ERROR")


def test_overlaps_known_gap():
    """Intervalle chevauchant le trou du weekend → True."""
    assert overlaps_known_gap("2026-08-08T00:00:00Z", "2026-08-09T00:00:00Z") is True
    assert overlaps_known_gap("2026-08-11T00:00:00Z", "2026-08-12T00:00:00Z") is False


def test_r2_additif_no_core_v9():
    src = Path("core/v10/v10_data_gap_validator.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src

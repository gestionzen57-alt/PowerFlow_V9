"""tests/test_v9_cvd_sentinel.py — Tests du sentinel CVD 6/6 M1.

Doctrine : R4 (données stale rejetées), R8 (test du nouveau composant).

Vérifie :
- 6 paires attendues
- Calcul de couverture correct
- Statut global OK/DEGRADED
- Idempotence (DB absente = erreur propre, pas crash)
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.v9_cvd_sentinel import check, EXPECTED_PAIRS  # noqa: E402


@pytest.fixture
def temp_db():
    """Crée une DB temporaire avec table forces_snapshots."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY,
            symbol TEXT,
            timeframe TEXT,
            timestamp TEXT,
            cvd_delta INTEGER
        )
        """
    )
    conn.commit()
    conn.close()
    yield Path(db_path)
    Path(db_path).unlink(missing_ok=True)


def test_expected_pairs_count():
    """6 paires surveillées (cf. doctrine multi-paires)."""
    assert len(EXPECTED_PAIRS) == 6
    assert "EURUSD" in EXPECTED_PAIRS
    assert "GBPUSD" in EXPECTED_PAIRS
    assert "USDJPY" in EXPECTED_PAIRS
    assert "USDCAD" in EXPECTED_PAIRS
    assert "USDCHF" in EXPECTED_PAIRS
    assert "AUDUSD" in EXPECTED_PAIRS


def test_check_db_missing_returns_error():
    """DB absente → erreur explicite, pas de crash."""
    with patch("scripts.v9_cvd_sentinel.DB_PATH", Path("/nonexistent/path.db")):
        result = check(15, 80.0)
    assert "error" in result


def test_check_all_ok(temp_db):
    """6/6 paires vivantes → status OK global."""
    with patch("scripts.v9_cvd_sentinel.DB_PATH", temp_db):
        conn = sqlite3.connect(str(temp_db))
        for sym in EXPECTED_PAIRS:
            for i in range(10):
                conn.execute(
                    "INSERT INTO forces_snapshots (symbol, timeframe, timestamp, cvd_delta) "
                    "VALUES (?, 'M1', datetime('now', '-1 minute'), ?)",
                    (sym, 100 + i),
                )
        conn.commit()
        conn.close()
        result = check(15, 80.0)

    assert result["global_status"] == "OK"
    assert result["pairs_alive"] == 6
    assert result["pairs_total"] == 6
    for sym in EXPECTED_PAIRS:
        assert result["details"][sym]["status"] == "OK"
        assert result["details"][sym]["coverage_pct"] == 100.0
        assert result["details"][sym]["n_cvd"] == 10


def test_check_partial_degradation(temp_db):
    """1 paire KO → status DEGRADED global."""
    with patch("scripts.v9_cvd_sentinel.DB_PATH", temp_db):
        conn = sqlite3.connect(str(temp_db))
        # 5 paires OK
        for sym in EXPECTED_PAIRS[:5]:
            for i in range(10):
                conn.execute(
                    "INSERT INTO forces_snapshots (symbol, timeframe, timestamp, cvd_delta) "
                    "VALUES (?, 'M1', datetime('now', '-1 minute'), ?)",
                    (sym, 100 + i),
                )
        # AUDUSD KO : 0 ligne
        conn.commit()
        conn.close()
        result = check(15, 80.0)

    assert result["global_status"] == "DEGRADED"
    assert result["pairs_alive"] == 5
    assert result["pairs_total"] == 6
    assert result["details"]["AUDUSD"]["status"] == "KO"
    assert result["details"]["AUDUSD"]["n_total"] == 0
    assert result["details"]["AUDUSD"]["coverage_pct"] == 0.0


def test_check_partial_coverage(temp_db):
    """Couverture partielle (50%) < seuil 80% → status KO."""
    with patch("scripts.v9_cvd_sentinel.DB_PATH", temp_db):
        conn = sqlite3.connect(str(temp_db))
        for sym in EXPECTED_PAIRS:
            for i in range(10):
                # 5 lignes avec CVD, 5 sans
                cvd = 100 + i if i < 5 else None
                conn.execute(
                    "INSERT INTO forces_snapshots (symbol, timeframe, timestamp, cvd_delta) "
                    "VALUES (?, 'M1', datetime('now', '-1 minute'), ?)",
                    (sym, cvd),
                )
        conn.commit()
        conn.close()
        result = check(15, 80.0)

    assert result["global_status"] == "DEGRADED"
    for sym in EXPECTED_PAIRS:
        assert result["details"][sym]["coverage_pct"] == 50.0
        assert result["details"][sym]["status"] == "KO"


def test_check_threshold_boundary(temp_db):
    """Seuil exact : 80% = OK, 79.9% = KO."""
    with patch("scripts.v9_cvd_sentinel.DB_PATH", temp_db):
        conn = sqlite3.connect(str(temp_db))
        for sym in EXPECTED_PAIRS:
            # 8/10 = 80% → OK au seuil 80
            for i in range(10):
                cvd = 100 + i if i < 8 else None
                conn.execute(
                    "INSERT INTO forces_snapshots (symbol, timeframe, timestamp, cvd_delta) "
                    "VALUES (?, 'M1', datetime('now', '-1 minute'), ?)",
                    (sym, cvd),
                )
        conn.commit()
        conn.close()
        result = check(15, 80.0)

    assert result["global_status"] == "OK"
    for sym in EXPECTED_PAIRS:
        assert result["details"][sym]["coverage_pct"] == 80.0
        assert result["details"][sym]["status"] == "OK"

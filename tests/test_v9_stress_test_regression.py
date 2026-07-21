"""tests/test_v9_stress_test_regression.py — Tests du stress test régression.

Doctrine : R7 (tests verts), R22 (CLI lecture seule), R13 (observer d'abord).
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

from scripts.v9_stress_test_regression import (  # noqa: E402
    main,
    render_text,
    run_all_tests,
    test_drift_loop_idempotence as _test_drift_loop_idempotence,
    test_loop_breaker_density as _test_loop_breaker_density,
    test_nzd_currency_distribution as _test_nzd_currency_distribution,
)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY,
            snapshot_id TEXT,
            direction TEXT,
            principes_source TEXT,
            opened_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY,
            currency TEXT,
            timestamp TEXT,
            principle_id INTEGER
        )
        """
    )
    conn.commit()
    conn.close()
    yield Path(db_path)
    import gc
    gc.collect()
    Path(db_path).unlink(missing_ok=True)


def test_loop_breaker_density_no_dups(temp_db):
    """1 trade par snapshot → test passé."""
    conn = sqlite3.connect(str(temp_db))
    for i in range(10):
        conn.execute(
            "INSERT INTO paper_trades (snapshot_id, direction, opened_at) VALUES (?, 'haussiere', datetime('now', '-1 hour'))",
            (f"v9-{i}",),
        )
    conn.commit()
    conn.close()

    with patch("scripts.v9_stress_test_regression.DB_PATH", temp_db):
        result = _test_loop_breaker_density()
    assert result["passed"] is True
    assert result["max_per_snapshot"] == 1


def test_loop_breaker_density_detects_dups(temp_db):
    """Snapshot avec 3 trades → test échoué."""
    conn = sqlite3.connect(str(temp_db))
    for i in range(3):
        conn.execute(
            "INSERT INTO paper_trades (snapshot_id, direction, opened_at) VALUES ('v9-X', 'haussiere', datetime('now', '-1 hour'))"
        )
    conn.commit()
    conn.close()

    with patch("scripts.v9_stress_test_regression.DB_PATH", temp_db):
        result = _test_loop_breaker_density()
    assert result["passed"] is False
    assert result["max_per_snapshot"] == 3


def test_nzd_currency_column_missing(temp_db):
    """DB absente → skipped."""
    with patch("scripts.v9_stress_test_regression.DB_PATH", Path("/nonexistent.db")):
        result = _test_nzd_currency_distribution()
    assert "skipped" in result


def test_nzd_currency_distribution_uniform(temp_db):
    """Distribution uniforme 12.5% par devise → test passé."""
    conn = sqlite3.connect(str(temp_db))
    currencies = ["USD", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD"]
    for curr in currencies:
        for i in range(10):
            conn.execute(
                "INSERT INTO principle_evaluations (currency, timestamp, principle_id) VALUES (?, datetime('now', '-1 day'), ?)",
                (curr, i),
            )
    conn.commit()
    conn.close()

    with patch("scripts.v9_stress_test_regression.DB_PATH", temp_db):
        result = _test_nzd_currency_distribution()
    assert result["passed"] is True
    assert result["max_pct"] == 12.5


def test_nzd_currency_distribution_skewed(temp_db):
    """90% NZD → test échoué (drift NZD non corrigé)."""
    conn = sqlite3.connect(str(temp_db))
    conn.execute(
        "INSERT INTO principle_evaluations (currency, timestamp, principle_id) "
        "SELECT 'NZD', datetime('now', '-1 day'), id FROM (SELECT 1 AS id UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9 UNION SELECT 10)"
    )
    for i in range(1):  # 1 EUR
        conn.execute(
            "INSERT INTO principle_evaluations (currency, timestamp, principle_id) VALUES ('EUR', datetime('now', '-1 day'), ?)",
            (100 + i,),
        )
    conn.commit()
    conn.close()

    with patch("scripts.v9_stress_test_regression.DB_PATH", temp_db):
        result = _test_nzd_currency_distribution()
    assert result["passed"] is False
    assert result["max_pct"] > 50.0


def test_drift_loop_index_present_no_dups(temp_db):
    """Index présent + pas de doublons → test passé."""
    conn = sqlite3.connect(str(temp_db))
    conn.execute(
        "CREATE INDEX idx_pt_snap_dir_princ ON paper_trades(snapshot_id, direction, principes_source)"
    )
    conn.execute(
        "INSERT INTO paper_trades (snapshot_id, direction, principes_source) VALUES ('v9-X', 'haussiere', 'PRICE_LAG')"
    )
    conn.commit()
    conn.close()

    with patch("scripts.v9_stress_test_regression.DB_PATH", temp_db):
        result = _test_drift_loop_idempotence()
    assert result["passed"] is True
    assert result["index_present"] is True
    assert result["n_duplicates"] == 0


def test_drift_loop_index_missing(temp_db):
    """Index absent → test échoué."""
    with patch("scripts.v9_stress_test_regression.DB_PATH", temp_db):
        result = _test_drift_loop_idempotence()
    assert result["passed"] is False
    assert "fix motion #32" in result["details"]


def test_render_text_includes_verdict():
    """Le rendu texte contient le verdict global."""
    report = {
        "n_tests": 3,
        "n_passed": 3,
        "n_failed": 0,
        "n_skipped": 0,
        "all_passed": True,
        "tests": [
            {"test": "t1", "passed": True, "details": "OK"},
        ],
    }
    text = render_text(report)
    assert "TOUS OK" in text
    assert "🟢" in text


def test_main_runs(temp_db, capsys):
    """CLI main() tourne sans crash (rc peut être 0 ou 1 selon verdict)."""
    with patch("scripts.v9_stress_test_regression.DB_PATH", temp_db):
        with patch.object(sys, "argv", ["prog"]):
            rc = main()
    # rc peut être 0 (tous passés) ou 1 (au moins un échec) — les deux sont valides
    assert rc in (0, 1)
    captured = capsys.readouterr()
    assert "Stress Test" in captured.out


def test_main_json_output(temp_db, capsys):
    """CLI --json produit JSON valide."""
    with patch("scripts.v9_stress_test_regression.DB_PATH", temp_db):
        with patch.object(sys, "argv", ["prog", "--json"]):
            rc = main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "tests" in data
    assert "all_passed" in data


def test_run_all_tests_aggregates():
    """run_all_tests agrège correctement."""
    report = run_all_tests()
    assert report["n_tests"] == 3
    assert "tests" in report
    assert len(report["tests"]) == 3

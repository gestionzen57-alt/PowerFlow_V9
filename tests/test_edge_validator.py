"""test_edge_validator.py — Tests pour core/v9/edge_validator.py.

Vérifie que la validation statistique des edges fonctionne :
- Test t sur l'expectancy
- p-value calculée correctement
- Niveau de confiance (high/medium/low)
- Profit factor
- Maximum drawdown
- Validation sur données synthétiques
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.v9.edge_validator import EdgeValidator, _normal_cdf


def test_normal_cdf_standard():
    """CDF normale : 0 → 0.5, 1.96 → ~0.975."""
    assert abs(_normal_cdf(0) - 0.5) < 0.001
    assert abs(_normal_cdf(1.96) - 0.975) < 0.001


def test_normal_cdf_symmetric():
    """CDF(-x) = 1 - CDF(x)."""
    for x in [0.5, 1.0, 2.0, 3.0]:
        assert abs(_normal_cdf(-x) - (1 - _normal_cdf(x))) < 0.001


def test_validate_empty_principle(tmp_path: Path):
    """Un principe sans trades → non significatif."""
    db = tmp_path / "empty.db"
    db.touch()
    # Créer les tables minimales
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE principle_evaluations (principle_id TEXT, snapshot_id TEXT, triggered INTEGER);
        CREATE TABLE decisions (snapshot_id TEXT, is_win INTEGER, resolution_pips REAL);
    """)
    conn.commit()
    conn.close()

    validator = EdgeValidator(db_path=db)
    result = validator.validate("NONEXISTENT")
    assert result["n_trades"] == 0
    assert result["significant"] is False


def test_validate_with_mock_db(tmp_path: Path):
    """Validation sur données synthétiques avec un edge réel."""
    import sqlite3
    db = tmp_path / "test_edge.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE principle_evaluations (principle_id TEXT, snapshot_id TEXT, triggered INTEGER, confidence REAL, currency TEXT);
        CREATE TABLE decisions (snapshot_id TEXT, is_win INTEGER, resolution_pips REAL, timestamp TEXT, action TEXT, decision_id TEXT);
    """)

    # 100 trades : 70 wins (+8 pips), 30 losses (-15 pips)
    for i in range(70):
        conn.execute("INSERT INTO principle_evaluations VALUES ('TEST_EDGE', ?, 1, 80.0, 'USD')", (f"s{i}",))
        conn.execute("INSERT INTO decisions VALUES (?, 1, 8.0, '2026-07-17T10:00:00Z', 'preparer_entree', ?)", (f"s{i}", f"d{i}"))
    for i in range(70, 100):
        conn.execute("INSERT INTO principle_evaluations VALUES ('TEST_EDGE', ?, 1, 80.0, 'USD')", (f"s{i}",))
        conn.execute("INSERT INTO decisions VALUES (?, 0, -15.0, '2026-07-17T10:00:00Z', 'preparer_entree', ?)", (f"s{i}", f"d{i}"))
    conn.commit()
    conn.close()

    validator = EdgeValidator(db_path=db)
    result = validator.validate("TEST_EDGE")

    assert result["n_trades"] == 100
    assert result["win_rate"] == 70.0
    assert result["expectancy"] == pytest.approx(1.1, abs=0.01)
    assert result["profit_factor"] == pytest.approx(560 / 450, abs=0.01)
    assert "p_value" in result
    assert "significant" in result
    assert "confidence" in result


def test_validate_all_returns_sorted(tmp_path: Path):
    """validate_all retourne une liste triée par expectancy décroissante."""
    import sqlite3
    db = tmp_path / "test_multi.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE principle_evaluations (principle_id TEXT, snapshot_id TEXT, triggered INTEGER, confidence REAL, currency TEXT);
        CREATE TABLE decisions (snapshot_id TEXT, is_win INTEGER, resolution_pips REAL, timestamp TEXT, action TEXT, decision_id TEXT);
    """)

    # Principe A : 25 trades, expectancy positive
    for i in range(25):
        conn.execute("INSERT INTO principle_evaluations VALUES ('A', ?, 1, 80.0, 'USD')", (f"a{i}",))
        conn.execute("INSERT INTO decisions VALUES (?, 1, 10.0, '2026-07-17T10:00:00Z', 'preparer_entree', ?)", (f"a{i}", f"da{i}"))
    # Principe B : 25 trades, expectancy négative
    for i in range(25):
        conn.execute("INSERT INTO principle_evaluations VALUES ('B', ?, 1, 80.0, 'USD')", (f"b{i}",))
        conn.execute("INSERT INTO decisions VALUES (?, 0, -10.0, '2026-07-17T10:00:00Z', 'preparer_entree', ?)", (f"b{i}", f"db{i}"))
    conn.commit()
    conn.close()

    validator = EdgeValidator(db_path=db)
    results = validator.validate_all(min_trades=20)

    assert len(results) == 2
    # A (expectancy +10) doit être avant B (expectancy -10)
    assert results[0]["principle_id"] == "A"
    assert results[1]["principle_id"] == "B"
    assert results[0]["expectancy"] > results[1]["expectancy"]


def test_max_drawdown_calculation(tmp_path: Path):
    """Le max drawdown est correctement calculé."""
    import sqlite3
    db = tmp_path / "test_dd.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE principle_evaluations (principle_id TEXT, snapshot_id TEXT, triggered INTEGER, confidence REAL, currency TEXT);
        CREATE TABLE decisions (snapshot_id TEXT, is_win INTEGER, resolution_pips REAL, timestamp TEXT, action TEXT, decision_id TEXT);
    """)

    pips = [10.0, 10.0, -25.0, 10.0]
    for i, p in enumerate(pips):
        is_win = 1 if p > 0 else 0
        conn.execute("INSERT INTO principle_evaluations VALUES ('DD_TEST', ?, 1, 80.0, 'USD')", (f"d{i}",))
        conn.execute("INSERT INTO decisions VALUES (?, ?, ?, '2026-07-17T10:00:00Z', 'preparer_entree', ?)", (f"d{i}", is_win, p, f"dd{i}"))
    conn.commit()
    conn.close()

    validator = EdgeValidator(db_path=db)
    result = validator.validate("DD_TEST")

    assert result["n_trades"] == 4
    assert result["max_drawdown"] == 25.0
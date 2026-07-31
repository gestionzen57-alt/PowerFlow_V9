"""tests/test_v9_quick_audit.py — Tests pour v9_quick_audit."""
import json
import sqlite3
from pathlib import Path

import pytest


def test_check_1_tests():
    """check_1_tests compte les fichiers tests."""
    from scripts.v9_quick_audit import check_1_tests
    result = check_1_tests()
    assert result["status"] in ("PASS", "WARN", "ERROR")
    assert "n_test_files" in result


def test_check_2_db_integrity_missing(tmp_path):
    """check_2_db_integrity sur DB absente → ERROR."""
    from scripts.v9_quick_audit import check_2_db_integrity
    result = check_2_db_integrity(tmp_path / "absent.db")
    assert result["status"] == "ERROR"


def test_check_2_db_integrity_present(tmp_path):
    """check_2_db_integrity sur DB valide → PASS."""
    from scripts.v9_quick_audit import check_2_db_integrity
    db = tmp_path / "v9.db"
    # Creer une petite DB (< 1 GB)
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    result = check_2_db_integrity(db)
    assert result["status"] == "PASS"
    assert result["integrity"] == "ok"


def test_check_3_phase12_live():
    """check_3_phase12_live verifie le .env."""
    from scripts.v9_quick_audit import check_3_phase12_live
    result = check_3_phase12_live()
    # Le .env reel doit contenir V9_MT4_BRIDGE_ENABLED=1 (Phase 12 LIVE motion)
    assert result["status"] in ("PASS", "FAIL", "ERROR")


def test_check_5_mirror_db_missing(tmp_path):
    """check_5_mirror sur DB absente → ERROR."""
    from scripts.v9_quick_audit import check_5_mirror
    result = check_5_mirror(tmp_path / "absent.db")
    assert result["status"] == "ERROR"


def test_check_5_mirror_with_table(tmp_path):
    """check_5_mirror avec table vide → INFO."""
    from scripts.v9_quick_audit import check_5_mirror
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE v9_human_trades (id INTEGER)")
        conn.commit()
    result = check_5_mirror(db)
    assert result["n_human_trades"] == 0
    assert result["status"] == "INFO"


def test_check_5_mirror_with_data(tmp_path):
    """check_5_mirror avec 25 trades → PASS."""
    from scripts.v9_quick_audit import check_5_mirror
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE v9_human_trades (id INTEGER)")
        for i in range(25):
            conn.execute("INSERT INTO v9_human_trades VALUES (?)", (i,))
        conn.commit()
    result = check_5_mirror(db)
    assert result["n_human_trades"] == 25
    assert result["status"] == "PASS"


def test_check_7_audit_sql_30j_db_missing(tmp_path):
    """check_7 sur DB absente → ERROR."""
    from scripts.v9_quick_audit import check_7_audit_sql_30j
    result = check_7_audit_sql_30j(tmp_path / "absent.db")
    assert result["status"] == "ERROR"


def test_check_7_audit_sql_30j_empty(tmp_path):
    """check_7 sur DB sans trades → INFO."""
    from scripts.v9_quick_audit import check_7_audit_sql_30j
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY,
                pips_net REAL, closed_at TEXT
            )
        """)
        conn.commit()
    result = check_7_audit_sql_30j(db)
    assert result["status"] == "INFO"
    assert result["n_total"] == 0


def test_check_7_audit_sql_30j_pass(tmp_path):
    """check_7 avec 30 trades WR 80% → PASS."""
    from scripts.v9_quick_audit import check_7_audit_sql_30j
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY,
                pips_net REAL, closed_at TEXT
            )
        """)
        # 24 wins + 6 losses = 80% WR
        for p in [25.0] * 24 + [-8.0] * 6:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')
            """, (p,))
        conn.commit()
    result = check_7_audit_sql_30j(db)
    assert result["n_total"] == 30
    assert result["wr_pct"] == 80.0
    assert result["status"] == "PASS"


def test_check_8_stress_test():
    """check_8 stress test avec mock data."""
    from scripts.v9_quick_audit import check_8_stress_test
    result = check_8_stress_test()
    assert result["status"] == "PASS"
    assert result["n_scenarios"] == 5


def test_check_9_edge_baseline():
    """check_9 edge baseline Phase 15."""
    from scripts.v9_quick_audit import check_9_edge_baseline
    result = check_9_edge_baseline()
    assert result["wr_baseline"] == 94.6
    assert result["status"] == "PASS"


def test_run_full_audit_smoke(tmp_path, monkeypatch, capsys):
    """run_full_audit execute tous les checks."""
    from scripts.v9_quick_audit import run_full_audit
    # Mock DB_PATH
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY,
                pips_net REAL, closed_at TEXT
            )
        """)
        for p in [25.0] * 24 + [-8.0] * 6:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')
            """, (p,))
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    # Mock REPORTS_PATH
    monkeypatch.setattr("scripts.v9_quick_audit.REPORT_PATH",
                        tmp_path / "audit.json")
    report = run_full_audit()
    assert "summary" in report
    assert "checks" in report
    assert report["summary"]["n_total"] == 10
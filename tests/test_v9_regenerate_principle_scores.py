"""Tests — scripts/v9_regenerate_principle_scores.py (Brief O1, 2026-07-12).

Couvre :
- _fetch_resolved_with_principles — filtre is_win NOT NULL + principes_json non vide
- regenerate() dry-run — ne modifie rien (table créée mais vide, cohérent
  avec la convention idempotente déjà utilisée par _ensure_perf_index)
- regenerate() apply — repeuple principle_scores depuis zéro (DELETE puis
  reconstruction), pas de double comptage sur un 2e run
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_regenerate_principle_scores as regen  # noqa: E402


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "regen_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE decisions (
            decision_id TEXT,
            action TEXT,
            is_win INTEGER,
            resolution_pips REAL,
            resolved_at TEXT,
            timestamp TEXT,
            principes_json TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO decisions VALUES "
        "('D1', 'preparer_entree', 1, 10.0, '2026-07-12T01:00:00+00:00', "
        " '2026-07-12T00:00:00+00:00', '[\"PRICE_LAG_AT_NODE_BIRTH\"]')"
    )
    conn.execute(
        "INSERT INTO decisions VALUES "
        "('D2', 'preparer_entree', 0, -5.0, '2026-07-12T02:00:00+00:00', "
        " '2026-07-12T01:00:00+00:00', '[\"PRICE_LAG_AT_NODE_BIRTH\"]')"
    )
    # Non résolue -> exclue
    conn.execute(
        "INSERT INTO decisions VALUES "
        "('D3', 'preparer_entree', NULL, NULL, NULL, "
        " '2026-07-12T02:00:00+00:00', '[\"PRICE_LAG_AT_NODE_BIRTH\"]')"
    )
    # Résolue mais sans principe -> exclue
    conn.execute(
        "INSERT INTO decisions VALUES "
        "('D4', 'preparer_entree', 1, 5.0, '2026-07-12T03:00:00+00:00', "
        " '2026-07-12T02:00:00+00:00', '[]')"
    )
    conn.commit()
    conn.close()
    return db


def test_fetch_resolved_with_principles_filters_correctly(temp_db: Path):
    from core.v9.db_schema import get_connection
    conn = get_connection(temp_db)
    conn.row_factory = sqlite3.Row
    try:
        ids = regen._fetch_resolved_with_principles(conn)
        assert ids == ["D1", "D2"]
    finally:
        conn.close()


def test_regenerate_dry_run_does_not_populate(temp_db: Path):
    result = regen.regenerate(temp_db, apply=False)
    assert result["dry_run"] is True
    assert result["n_target_decisions"] == 2

    conn = sqlite3.connect(str(temp_db))
    n = conn.execute("SELECT COUNT(*) FROM principle_scores").fetchone()[0]
    conn.close()
    assert n == 0


def test_regenerate_apply_populates_scores(temp_db: Path):
    result = regen.regenerate(temp_db, apply=True)
    assert result["dry_run"] is False
    assert result["n_decisions_scored"] == 2

    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT n_trades, n_wins, win_rate FROM principle_scores "
            "WHERE principle_id='PRICE_LAG_AT_NODE_BIRTH' AND combination_hash IS NULL"
        ).fetchone()
        assert row["n_trades"] == 2
        assert row["n_wins"] == 1
        assert row["win_rate"] == 50.0
    finally:
        conn.close()


def test_regenerate_apply_twice_no_double_counting(temp_db: Path):
    regen.regenerate(temp_db, apply=True)
    result2 = regen.regenerate(temp_db, apply=True)
    assert result2["n_decisions_scored"] == 2

    conn = sqlite3.connect(str(temp_db))
    row = conn.execute(
        "SELECT n_trades FROM principle_scores "
        "WHERE principle_id='PRICE_LAG_AT_NODE_BIRTH' AND combination_hash IS NULL"
    ).fetchone()
    conn.close()
    assert row[0] == 2  # pas 4 — le DELETE FROM avant reconstruction évite le double comptage


def test_main_dry_run_writes_no_report(temp_db: Path, tmp_path: Path):
    report_path = tmp_path / "report.json"
    rc = regen.main(["--db", str(temp_db), "--dry-run", "--report", str(report_path)])
    assert rc == 0
    assert not report_path.exists()


def test_main_apply_writes_report(temp_db: Path, tmp_path: Path):
    report_path = tmp_path / "report.json"
    rc = regen.main(["--db", str(temp_db), "--apply", "--report", str(report_path)])
    assert rc == 0
    assert report_path.exists()
    parsed = json.loads(report_path.read_text(encoding="utf-8"))
    assert parsed["n_decisions_scored"] == 2

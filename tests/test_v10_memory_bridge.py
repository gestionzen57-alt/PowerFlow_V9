"""V10 Memory Bridge — tests unitaires (Phase 1, Cognitive Continuum).

Obligations :
  1. test_recall_no_db_r6
  2. test_recall_empty_table
  3. test_recall_with_data
  4. test_transition_no_table
  5. test_memory_summary_no_db
  6. test_r2_additif_no_core_v9
"""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_memory_bridge import (  # noqa: E402
    recall_patterns,
    get_transition_distribution,
    memory_summary,
)


def _make_db(path: Path):
    """Crée une DB cycle_patterns de test (schéma réel V9)."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cycle_patterns (
            symbol TEXT, timeframe TEXT, regime_type TEXT, phase TEXT,
            vol_atr_bucket TEXT, n_observations INTEGER, n_wins INTEGER,
            n_resolved INTEGER, n_pending INTEGER, sum_duration REAL,
            sum_duration_sq REAL, max_duration REAL, p50_duration REAL,
            p95_duration REAL, last_updated_ts REAL
        )
    """)
    conn.execute("""
        INSERT INTO cycle_patterns VALUES
        ('EURUSD','H1','NEUTRE','culmination','MEDIUM',40,20,30,10,0,0,0,0,0,1785239385),
        ('EURUSD','H1','EXTENSION','developpement','LOW',10,4,8,2,0,0,0,0,0,1785239385)
    """)
    conn.commit()
    conn.close()


def test_recall_no_db_r6(tmp_path):
    assert recall_patterns("EURUSD", "H1", db_path=tmp_path / "absent.db") == []


def test_recall_empty_table(tmp_path):
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE cycle_patterns (symbol TEXT)")
    conn.commit()
    conn.close()
    assert recall_patterns("EURUSD", "H1", db_path=db) == []


def test_recall_with_data(tmp_path):
    db = tmp_path / "mem.db"
    _make_db(db)
    res = recall_patterns("EURUSD", "H1", db_path=db)
    assert len(res) == 2
    assert res[0]["wr"] == pytest.approx(0.667, abs=0.01)  # 20/30
    assert res[0]["n_observations"] == 40


def test_transition_no_table(tmp_path):
    db = tmp_path / "notrans.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE cycle_patterns (symbol TEXT)")
    conn.commit()
    conn.close()
    assert get_transition_distribution("culmination", db_path=db) == {}


def test_memory_summary_no_db(tmp_path):
    s = memory_summary(db_path=tmp_path / "absent.db")
    assert s["status"] == "no_db"
    assert s["n_patterns"] == 0


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_memory_bridge.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src

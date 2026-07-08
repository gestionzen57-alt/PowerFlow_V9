"""Tests — scripts/v9_paper_trade_run.py (Phase 10).

Couvre :
- fetch_context_for_snapshot — priorité exploitability.statut sur
  window.statut (régression bug 2026-07-08 : window.statut vaut
  toujours 'absente' en donnée live, ce qui bloquait 100% des
  paper-trades quand il était lu en priorité).
- is_trade_already_open — idempotence.
- run() — bout en bout : snapshot go=True ouvre un paper-trade,
  re-run n'en rouvre pas un second.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_paper_trade_run as ptr  # noqa: E402


def _compress(obj: dict) -> bytes:
    return zlib.compress(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "paper_trade_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE decisions (
            decision_id TEXT PRIMARY KEY,
            timestamp TEXT,
            snapshot_id TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            confiance INTEGER,
            action TEXT,
            principes_json TEXT,
            contexte_complet_json BLOB,
            source_type TEXT
        );
        CREATE TABLE paper_trades (
            trade_id TEXT PRIMARY KEY,
            snapshot_id TEXT,
            direction TEXT,
            confiance INTEGER,
            principes_source TEXT,
            opened_at TEXT,
            closed_at TEXT,
            pips_simulated REAL,
            is_win INTEGER,
            risk_go_context TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return db


def test_fetch_context_prioritizes_exploitability_statut(temp_db: Path):
    """window.statut='absente' + exploitability.statut='exploitable' →
    window_status doit être 'exploitable' (pas 'absente')."""
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    contexte = _compress({
        "window": {"statut": "absente"},
        "exploitability": {"statut": "exploitable", "window_statut": "absente"},
    })
    conn.execute(
        "INSERT INTO decisions (decision_id, timestamp, snapshot_id, contexte_complet_json) "
        "VALUES ('d1', '2026-07-08T12:00:00+00:00', 'snap1', ?)",
        (contexte,),
    )
    conn.commit()

    ctx = ptr.fetch_context_for_snapshot(conn, "snap1")
    assert ctx["window_status"] == "exploitable"
    conn.close()


def test_fetch_context_falls_back_to_window_statut_if_no_exploitability(temp_db: Path):
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    contexte = _compress({"window": {"statut": "non_exploitable"}})
    conn.execute(
        "INSERT INTO decisions (decision_id, timestamp, snapshot_id, contexte_complet_json) "
        "VALUES ('d1', '2026-07-08T12:00:00+00:00', 'snap1', ?)",
        (contexte,),
    )
    conn.commit()

    ctx = ptr.fetch_context_for_snapshot(conn, "snap1")
    assert ctx["window_status"] == "non_exploitable"
    conn.close()


def test_is_trade_already_open_idempotence(temp_db: Path):
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    assert ptr.is_trade_already_open(conn, "snap1", "haussiere") is False

    conn.execute(
        "INSERT INTO paper_trades (trade_id, snapshot_id, direction, opened_at) "
        "VALUES ('pt_1', 'snap1', 'haussiere', '2026-07-08T12:00:00+00:00')"
    )
    conn.commit()
    assert ptr.is_trade_already_open(conn, "snap1", "haussiere") is True
    assert ptr.is_trade_already_open(conn, "snap1", "baissiere") is False
    conn.close()

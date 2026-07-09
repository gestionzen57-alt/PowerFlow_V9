"""Tests — scripts/v9_replay_doctrine_realign.py (Phase C6 doctrine realign).

Couvre :
- _build_vote() — pluralité, égalité -> neutre, confiance/horizon
- replay_snapshot() — filtre currency base/quote, compare pre vs post
- replay_window() — filtre temporel + symbole
- Cas structurel : les 17 principes newly-ACTIVE (kind=grammar, 0 conditions)
  ne peuvent jamais différer pre/post (triggered=0 toujours pour eux côté DB
  réelle) — ici testé via des lignes synthétiques triggered=0 explicites.
"""

from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_replay_doctrine_realign as replay  # noqa: E402


# ── _build_vote ──────────────────────────────────────────────
def _row(principle_id: str, currency: str, triggered: bool, direction, confidence):
    return {
        "principle_id": principle_id, "currency": currency,
        "triggered": triggered, "direction": direction, "confidence": confidence,
    }


class _DictRow(dict):
    """sqlite3.Row-like : accès par clé, comme utilisé par _build_vote."""

    def __getitem__(self, key):
        return dict.get(self, key)


def _rows(*specs):
    return [_DictRow(_row(*s)) for s in specs]


def test_build_vote_majority_direction():
    rows = _rows(
        ("ZONE_RETEST", "GBP", True, "haussiere", 80),
        ("NODE_BIRTH_FAST", "GBP", True, "haussiere", 70),
        ("RAW_NODE_BIRTH", "USD", True, "baissiere", 60),
    )
    result = replay._build_vote(rows, replay.PRE_PATCH_ACTIVE_IDS, 65)
    assert result["direction"] == "haussiere"
    assert result["n_triggered"] == 3


def test_build_vote_tie_returns_neutre():
    rows = _rows(
        ("ZONE_RETEST", "GBP", True, "haussiere", 80),
        ("NODE_BIRTH_FAST", "GBP", True, "baissiere", 70),
    )
    result = replay._build_vote(rows, replay.PRE_PATCH_ACTIVE_IDS, 65)
    assert result["direction"] == "neutre"


def test_build_vote_excludes_ids_outside_active_set():
    rows = _rows(
        ("GRAMMAR_ABSORPTION", "GBP", True, "haussiere", 90),  # hors PRE_PATCH_ACTIVE_IDS
    )
    result = replay._build_vote(rows, replay.PRE_PATCH_ACTIVE_IDS, 65)
    assert result["direction"] == "neutre"
    assert result["n_triggered"] == 0


def test_build_vote_never_triggered_grammar_identical_pre_post():
    # Simule le cas réel : un principe grammar (conditions vides) n'est
    # JAMAIS triggered=1 en DB, donc absent des deux ensembles filtrés.
    rows = _rows(
        ("ZONE_RETEST", "GBP", True, "haussiere", 80),
        ("GRAMMAR_ABSORPTION", "GBP", False, None, None),
    )
    pre = replay._build_vote(rows, replay.PRE_PATCH_ACTIVE_IDS, 65)
    post = replay._build_vote(rows, replay.POST_PATCH_ACTIVE_IDS, 65)
    assert pre["direction"] == post["direction"] == "haussiere"
    assert pre["confiance"] == post["confiance"]


def test_pre_patch_active_ids_is_10_post_is_25_all_promoted():
    # PRE_PATCH = 10 historiques (avant toute promotion).
    # POST_PATCH = config.PRINCIPLE_ACTIVE_IDS = 25 (promotion massive 2026-07-10).
    assert len(replay.PRE_PATCH_ACTIVE_IDS) == 10
    assert len(replay.POST_PATCH_ACTIVE_IDS) == 25
    assert "GRAMMAR_CONTEXTE" in replay.POST_PATCH_ACTIVE_IDS
    assert "GRAMMAR_CONTEXTE" not in replay.PRE_PATCH_ACTIVE_IDS
    assert "GRAMMAR_ABSORPTION" in replay.POST_PATCH_ACTIVE_IDS
    assert "GRAMMAR_TENSION" in replay.POST_PATCH_ACTIVE_IDS


# ── replay_snapshot / replay_window (DB temporaire) ──────────
@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "replay_doctrine.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE principle_evaluations (
            evaluation_id TEXT UNIQUE,
            timestamp TEXT,
            snapshot_id TEXT,
            principle_id TEXT,
            symbol TEXT,
            currency TEXT,
            triggered INTEGER,
            direction TEXT,
            confidence INTEGER
        );
        """
    )
    conn.close()
    return db


def _insert_eval(db: Path, **kw) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO principle_evaluations "
        "(evaluation_id, timestamp, snapshot_id, principle_id, symbol, currency, "
        "triggered, direction, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"peval-{uuid.uuid4().hex[:8]}", kw["timestamp"], kw["snapshot_id"],
            kw["principle_id"], kw["symbol"], kw["currency"], kw["triggered"],
            kw.get("direction"), kw.get("confidence"),
        ),
    )
    conn.commit()
    conn.close()


def test_replay_snapshot_identique_when_only_node_rule_triggers(temp_db: Path):
    _insert_eval(
        temp_db, timestamp="2026-07-08T10:00:00Z", snapshot_id="snap-1",
        principle_id="ZONE_RETEST", symbol="GBPUSD", currency="GBP",
        triggered=1, direction="haussiere", confidence=80,
    )
    _insert_eval(
        temp_db, timestamp="2026-07-08T10:00:00Z", snapshot_id="snap-1",
        principle_id="GRAMMAR_ABSORPTION", symbol="GBPUSD", currency="GBP",
        triggered=0, direction=None, confidence=None,
    )
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    try:
        result = replay.replay_snapshot(conn, "snap-1", "GBPUSD", 65)
    finally:
        conn.close()
    assert result["identique"] is True
    assert result["pre"]["direction"] == "haussiere"
    assert result["post"]["direction"] == "haussiere"


def test_replay_window_filters_by_time_and_symbol(temp_db: Path):
    _insert_eval(
        temp_db, timestamp="2026-07-08T10:00:00Z", snapshot_id="snap-in",
        principle_id="ZONE_RETEST", symbol="GBPUSD", currency="GBP",
        triggered=1, direction="haussiere", confidence=80,
    )
    _insert_eval(
        temp_db, timestamp="2026-01-01T00:00:00Z", snapshot_id="snap-out-of-window",
        principle_id="ZONE_RETEST", symbol="GBPUSD", currency="GBP",
        triggered=1, direction="haussiere", confidence=80,
    )
    _insert_eval(
        temp_db, timestamp="2026-07-08T10:00:00Z", snapshot_id="snap-other-symbol",
        principle_id="ZONE_RETEST", symbol="EURUSD", currency="EUR",
        triggered=1, direction="haussiere", confidence=80,
    )
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    try:
        results = replay.replay_window(
            conn, "2026-07-08T00:00:00Z", "2026-07-08T23:59:59Z", "GBPUSD", 65
        )
    finally:
        conn.close()
    assert [r["snapshot_id"] for r in results] == ["snap-in"]


def test_connect_raises_on_missing_db(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        replay._connect(tmp_path / "does_not_exist.db")

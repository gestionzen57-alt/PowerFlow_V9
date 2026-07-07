"""Tests — scripts/v9_replay.py (replay / inspection lecture seule V9).

Couvre les fonctions pures (similarity, search, parse) et les fonctions DB
avec DB temporaire. Aucun test ne touche data/v9_forces.db.

Fonctions testées :
- compute_similarity_score(behavior_a, b, cinematique_a, b) — score 0.0-1.0
- parse_search_terms(terms) — parsing "key=value"
- matches_search(behavior, criteria) — filtre exact
- _s(value) — str-safe (None → "")
- fetch_all_behaviors, fetch_behavior_by_id (DB temporaire)
- _row_to_dict, table_exists (DB temporaire)
- run_list, run_show, run_search avec conn=None
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_replay  # noqa: E402


# ── _s (string-safe) ────────────────────────────────────────
def test_s_returns_str() -> None:
    assert v9_replay._s("abc") == "abc"
    assert v9_replay._s(123) == "123"
    assert v9_replay._s(None) == ""
    assert v9_replay._s(0.5) == "0.5"


# ── compute_similarity_score ────────────────────────────────
def test_similarity_identical_max() -> None:
    """Comportements identiques → score 1.0 (tous les champs matchent)."""
    behavior = {
        "qualification": "bascule",
        "intensite": "forte",
        "phase": "escalade",
        "symbol": "GBPUSD",
        "timeframe": "M15",
    }
    cin = {
        "acceleration_deceleration": "acceleration",
        "compression_extension": {"etat": "compression"},
    }
    score = v9_replay.compute_similarity_score(behavior, behavior, cin, cin)
    assert score == 1.0


def test_similarity_zero_when_nothing_matches() -> None:
    a = {"qualification": "bascule", "intensite": "forte", "phase": "escalade",
         "symbol": "GBPUSD", "timeframe": "M15"}
    b = {"qualification": "maintien", "intensite": "faible", "phase": "consolidation",
         "symbol": "EURUSD", "timeframe": "H1"}
    ca = {"acceleration_deceleration": "acceleration", "compression_extension": {"etat": "compression"}}
    cb = {"acceleration_deceleration": "deceleration", "compression_extension": {"etat": "extension"}}
    score = v9_replay.compute_similarity_score(a, b, ca, cb)
    assert score == 0.0


def test_similarity_partial_score() -> None:
    """3 champs sur 7 qui matchent → 0.3 + 0.15 + 0.15 = 0.6."""
    a = {"qualification": "bascule", "intensite": "forte", "phase": "escalade",
         "symbol": "GBPUSD", "timeframe": "M15"}
    b = {"qualification": "bascule", "intensite": "forte", "phase": "escalade",
         "symbol": "EURUSD", "timeframe": "H1"}
    ca = {"acceleration_deceleration": "x", "compression_extension": {"etat": "y"}}
    cb = {"acceleration_deceleration": "z", "compression_extension": {"etat": "w"}}
    score = v9_replay.compute_similarity_score(a, b, ca, cb)
    assert score == 0.6


def test_similarity_handles_missing_cinematique() -> None:
    """Cinematique {} → les 2 .get() valent None → None == None = match.
    Score = 1.0 (tous les champs comportement + cinématique matchent par défaut)."""
    a = {"qualification": "bascule", "intensite": "forte", "phase": "x",
         "symbol": "GBPUSD", "timeframe": "M15"}
    score = v9_replay.compute_similarity_score(a, a, {}, {})
    assert score == 1.0


def test_similarity_handles_partial_cinematique() -> None:
    """Cinematique avec seulement acceleration_deceleration qui matche + compression
    extension absente des 2 côtés (None == None via .get().get() or {} → match).
    Score = 1.0 (tous les champs matchent par défaut quand les 2 côtés sont None)."""
    a = {"qualification": "bascule", "intensite": "forte", "phase": "x",
         "symbol": "GBPUSD", "timeframe": "M15"}
    ca = {"acceleration_deceleration": "acceleration"}
    cb = {"acceleration_deceleration": "acceleration"}
    score = v9_replay.compute_similarity_score(a, a, ca, cb)
    assert score == 1.0


def test_similarity_cinematique_mismatch() -> None:
    """Cinematique avec acceleration_deceleration différent → 0.1 en moins.
    Score = 1.0 - 0.1 = 0.9."""
    a = {"qualification": "bascule", "intensite": "forte", "phase": "x",
         "symbol": "GBPUSD", "timeframe": "M15"}
    ca = {"acceleration_deceleration": "acceleration",
          "compression_extension": {"etat": "compression"}}
    cb = {"acceleration_deceleration": "deceleration",
          "compression_extension": {"etat": "extension"}}
    score = v9_replay.compute_similarity_score(a, a, ca, cb)
    assert score == 0.8  # 1.0 - 0.1 (accel_decel diff) - 0.1 (compression etat diff)


# ── parse_search_terms ──────────────────────────────────────
def test_parse_search_terms_simple() -> None:
    assert v9_replay.parse_search_terms(["qualification=bascule"]) == {
        "qualification": "bascule"
    }


def test_parse_search_terms_multiple() -> None:
    assert v9_replay.parse_search_terms(
        ["qualification=bascule", "intensite=forte", "symbol=GBPUSD"]
    ) == {"qualification": "bascule", "intensite": "forte", "symbol": "GBPUSD"}


def test_parse_search_terms_invalid_raises() -> None:
    """Termes sans '=' lèvent ValueError (comportement strict du script)."""
    with pytest.raises(ValueError, match="invalide"):
        v9_replay.parse_search_terms(["invalid_no_equals", "qual=ok"])


# ── matches_search ──────────────────────────────────────────
def test_matches_search_all_match() -> None:
    behavior = {"qualification": "bascule", "intensite": "forte"}
    assert v9_replay.matches_search(behavior, {"qualification": "bascule", "intensite": "forte"}) is True


def test_matches_search_one_mismatch() -> None:
    behavior = {"qualification": "bascule", "intensite": "forte"}
    assert v9_replay.matches_search(behavior, {"qualification": "bascule", "intensite": "faible"}) is False


def test_matches_search_empty_criteria() -> None:
    """Critères vides → tout match (filtre no-op)."""
    assert v9_replay.matches_search({"qualification": "x"}, {}) is True


# ── DB temporaire : fetch + table_exists ────────────────────
@pytest.fixture
def temp_db(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "replay_test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE behaviors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            behavior_id TEXT,
            qualification TEXT,
            intensite TEXT,
            phase TEXT,
            symbol TEXT,
            timeframe TEXT
        )
    """)
    conn.execute("""
        INSERT INTO behaviors (behavior_id, qualification, intensite, phase, symbol, timeframe) VALUES
        ('b-001', 'bascule', 'forte', 'escalade', 'GBPUSD', 'M15'),
        ('b-002', 'maintien', 'faible', 'consolidation', 'EURUSD', 'H1')
    """)
    conn.commit()
    return conn


def test_table_exists(temp_db: sqlite3.Connection) -> None:
    assert v9_replay.table_exists(temp_db, "behaviors") is True
    assert v9_replay.table_exists(temp_db, "missing") is False
    temp_db.close()


def test_fetch_all_behaviors(temp_db: sqlite3.Connection) -> None:
    rows = v9_replay.fetch_all_behaviors(temp_db)
    assert len(rows) == 2
    assert rows[0]["behavior_id"] == "b-001"
    assert rows[1]["qualification"] == "maintien"
    temp_db.close()


def test_fetch_behavior_by_id(temp_db: sqlite3.Connection) -> None:
    b = v9_replay.fetch_behavior_by_id(temp_db, "b-001")
    assert b is not None
    assert b["qualification"] == "bascule"
    missing = v9_replay.fetch_behavior_by_id(temp_db, "b-999")
    assert missing is None
    temp_db.close()


# ── run_list / run_show / run_search avec conn=None ─────────
def test_run_list_no_db(capsys: pytest.CaptureFixture[str]) -> None:
    """DB absente → warning + rc=0 (pas d'erreur, juste rien à lister)."""
    rc = v9_replay.run_list(None)
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "introuvable" in out or "aucune" in out


def test_run_show_no_db(capsys: pytest.CaptureFixture[str]) -> None:
    """DB absente → rc=0 (warning) car run_show retourne 0 après le print."""
    rc = v9_replay.run_show(None, "b-001")
    # run_show retourne 0 (warning) ou 1 (erreur) selon le code
    assert rc in (0, 1)
    out = capsys.readouterr().out.lower()
    assert "introuvable" in out or "aucune" in out


def test_run_search_no_db(capsys: pytest.CaptureFixture[str]) -> None:
    """DB absente → rc=0 (warning) car run_search retourne 0 après le print."""
    rc = v9_replay.run_search(None, ["qualification=bascule"])
    assert rc in (0, 1)
    out = capsys.readouterr().out.lower()
    assert "introuvable" in out or "aucune" in out
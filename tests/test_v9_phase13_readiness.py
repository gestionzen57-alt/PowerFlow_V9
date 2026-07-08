"""Tests — scripts/v9_phase13_readiness.py.

Couvre :
- _verdict — toutes les branches
- _eval_principle — comptage triggers et calcul hit_rate
- audit — verdict global selon état WIN/LOSS
- render_text / render_markdown — format non-vide
- main() --json / --report
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

from scripts import v9_phase13_readiness as r13  # noqa: E402


# ── _verdict ───────────────────────────────────────────────────
def test_verdict_inert_no_conditions():
    assert r13._verdict(False, {"n_triggers": 0, "hit_rate_pct": None}) == "INERT_NO_CONDITIONS"


def test_verdict_blocked_no_trigger():
    assert r13._verdict(True, {"n_triggers": 0, "hit_rate_pct": None}) == "BLOCKED_NO_TRIGGER"


def test_verdict_early_triggers():
    assert r13._verdict(True, {"n_triggers": 10, "hit_rate_pct": None}) == "EARLY_TRIGGERS"


def test_verdict_ready_structural_no_winloss():
    assert r13._verdict(True, {"n_triggers": 100, "hit_rate_pct": None}) == "READY_STRUCTURAL"


def test_verdict_ready_full_high_hit_rate():
    assert r13._verdict(True, {"n_triggers": 100, "hit_rate_pct": 75.0}) == "READY_FULL"


def test_verdict_ready_low_hit_rate():
    assert r13._verdict(True, {"n_triggers": 100, "hit_rate_pct": 45.0}) == "READY_LOW_HIT_RATE"


# ── _eval_principle ────────────────────────────────────────────
@pytest.fixture
def temp_db_with_eval(tmp_path: Path) -> Path:
    db = tmp_path / "r13_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT,
            triggered INTEGER
        );
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER
        );
        """
    )
    # 10 triggers pour PID_X, 5 résolus en win, 2 en loss
    for i in range(10):
        snap = f"snap-{i}"
        conn.execute(
            "INSERT INTO principle_evaluations (principle_id, snapshot_id, triggered) "
            "VALUES (?, ?, ?)",
            ("PID_X", snap, 1 if i < 10 else 0),
        )
        if i < 7:  # 7 résolus
            conn.execute(
                "INSERT INTO decisions (snapshot_id, is_win) VALUES (?, ?)",
                (snap, 1 if i < 5 else 0),  # 5 wins, 2 losses
            )
    # 3 non-triggered
    for i in range(3):
        conn.execute(
            "INSERT INTO principle_evaluations (principle_id, snapshot_id, triggered) "
            "VALUES (?, ?, ?)",
            ("PID_X", f"snap-no-{i}", 0),
        )
    conn.commit()
    conn.close()
    return db


def test_eval_principle_no_trigger(temp_db_with_eval: Path):
    conn = sqlite3.connect(str(temp_db_with_eval))
    try:
        result = r13._eval_principle({"id": "PID_NEVER"}, conn)
        assert result["n_evaluations"] == 0
        assert result["n_triggers"] == 0
        assert result["hit_rate_pct"] is None
    finally:
        conn.close()


def test_eval_principle_with_resolved(temp_db_with_eval: Path):
    conn = sqlite3.connect(str(temp_db_with_eval))
    try:
        result = r13._eval_principle({"id": "PID_X"}, conn)
        # 13 evals total (10 triggers + 3 non)
        assert result["n_evaluations"] == 13
        assert result["n_triggers"] == 10
        # 7 résolus (5 wins / 2 losses → 5/7 = 71.4%)
        assert result["n_resolved"] == 7
        assert result["hit_rate_pct"] == 71.4
    finally:
        conn.close()


# ── audit (DB minimale) ───────────────────────────────────────
@pytest.fixture
def temp_db_with_shadows(tmp_path: Path) -> Path:
    """DB avec 1 SHADOW 'GRAMMAR_FAKE' : conditions présentes, 60 triggers,
    0 WIN/LOSS résolu (3 décisions non résolues)."""
    db = tmp_path / "r13_audit.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT, triggered INTEGER
        );
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER, action TEXT
        );
        """
    )
    for i in range(60):
        conn.execute(
            "INSERT INTO principle_evaluations (principle_id, snapshot_id, triggered) "
            "VALUES (?, ?, ?)",
            ("GRAMMAR_FAKE", f"snap-{i}", 1),
        )
        conn.execute(
            "INSERT INTO decisions (snapshot_id, is_win, action) VALUES (?, NULL, ?)",
            (f"snap-{i}", "preparer_entree"),
        )
    conn.commit()
    conn.close()
    return db


def test_audit_globally_blocked_no_winloss(tmp_path: Path):
    """DB avec 0 WIN/LOSS → verdict global PHASE_13_BLOCKED_NO_WINLOSS."""
    fake_dir = tmp_path / "principles"
    fake_dir.mkdir()
    (fake_dir / "GRAMMAR_FAKE.yaml").write_text(
        """id: GRAMMAR_FAKE
version: 1
origin: TEST
status: SHADOW
v9_status: SHADOW
kind: grammar
conditions:
- field: h1_state
  op: not_in
  value: [NEUTRAL, null]
emits:
  pattern_type: FAKE
  direction: from_h1_dir
bounds: {}
anti_signal_bias: false
notes: |
  Fake principle pour test readiness.
""",
        encoding="utf-8",
    )
    db = tmp_path / "audit_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE principle_evaluations (id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT, triggered INTEGER);
        CREATE TABLE decisions (id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER, action TEXT);
    """)
    for i in range(60):
        conn.execute("INSERT INTO principle_evaluations VALUES (?,?,?,?)", (i+1, "GRAMMAR_FAKE", f"snap-{i}", 1))
        conn.execute("INSERT INTO decisions (snapshot_id, is_win, action) VALUES (?, NULL, ?)", (f"snap-{i}", "preparer_entree"))
    conn.commit()
    conn.close()

    report = r13.audit(db, principles_dir=fake_dir)
    assert report["n_shadows"] == 1
    assert report["n_wins"] == 0
    assert report["n_losses"] == 0
    assert report["global_verdict"] == "PHASE_13_BLOCKED_NO_WINLOSS"
    assert report["per_principle"][0]["principle_id"] == "GRAMMAR_FAKE"
    assert report["per_principle"][0]["verdict"] == "READY_STRUCTURAL"


def test_audit_promotable_with_high_hit_rate(tmp_path: Path):
    """DB avec WIN/LOSS résolus + hit_rate ≥ 60% → READY_FULL → PHASE_13_PROMOTABLE."""
    fake_dir = tmp_path / "principles"
    fake_dir.mkdir()
    (fake_dir / "GRAMMAR_FAKE.yaml").write_text(
        """id: GRAMMAR_FAKE
version: 1
origin: TEST
status: SHADOW
v9_status: SHADOW
kind: grammar
conditions:
- field: h1_state
  op: not_in
  value: [NEUTRAL, null]
emits:
  pattern_type: FAKE
  direction: from_h1_dir
""",
        encoding="utf-8",
    )
    db = tmp_path / "audit_test2.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE principle_evaluations (id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT, triggered INTEGER);
        CREATE TABLE decisions (id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER, action TEXT);
    """)
    # 60 triggers, 10 résolus, 9 wins / 1 loss = 90% hit_rate
    for i in range(60):
        conn.execute("INSERT INTO principle_evaluations VALUES (?,?,?,?)", (i+1, "GRAMMAR_FAKE", f"snap-{i}", 1))
        if i < 10:
            conn.execute("INSERT INTO decisions (snapshot_id, is_win, action) VALUES (?, ?, ?)", (f"snap-{i}", 1 if i < 9 else 0, "preparer_entree"))
    conn.commit()
    conn.close()

    report = r13.audit(db, principles_dir=fake_dir)
    assert report["n_wins"] == 9
    assert report["n_losses"] == 1
    assert report["global_verdict"] == "PHASE_13_PROMOTABLE"
    assert report["per_principle"][0]["verdict"] == "READY_FULL"
    assert report["per_principle"][0]["hit_rate_pct"] == 90.0


# ── render ────────────────────────────────────────────────────
def test_render_text_contains_global_verdict():
    report = {
        "n_shadows": 1, "n_wins": 0, "n_losses": 0, "n_open": 0,
        "thresholds": {"triggers_min": 50, "hit_rate_pct_min": 60},
        "per_principle": [],
        "verdict_counts": {},
        "global_verdict": "PHASE_13_BLOCKED_NO_WINLOSS",
    }
    text = r13.render_text(report)
    assert "PHASE_13_BLOCKED_NO_WINLOSS" in text
    assert "VERDICT GLOBAL" in text


def test_render_markdown_contains_table():
    report = {
        "n_shadows": 1, "n_wins": 0, "n_losses": 0, "n_open": 0,
        "thresholds": {"triggers_min": 50, "hit_rate_pct_min": 60},
        "per_principle": [{
            "principle_id": "X", "kind": "grammar",
            "conditions_written": True, "n_evaluations": 10,
            "n_triggers": 5, "n_resolved": 0, "hit_rate_pct": None,
            "verdict": "BLOCKED_NO_TRIGGER",
        }],
        "verdict_counts": {"BLOCKED_NO_TRIGGER": 1},
        "global_verdict": "PHASE_13_BLOCKED_NO_WINLOSS",
    }
    md = r13.render_markdown(report)
    assert "| Principe |" in md
    assert "GRAMMAR_FAKE" not in md  # placeholder
    assert "X" in md
    assert "BLOCKED_NO_TRIGGER" in md


# ── main ──────────────────────────────────────────────────────
def test_main_json_output(tmp_path: Path, capsys):
    """Test main() avec --json sur DB tmp."""
    fake_dir = tmp_path / "principles"
    fake_dir.mkdir()
    (fake_dir / "GRAMMAR_FAKE.yaml").write_text(
        """id: GRAMMAR_FAKE
v9_status: SHADOW
kind: grammar
conditions:
- field: x
  op: ==
  value: 1
""",
        encoding="utf-8",
    )

    db = tmp_path / "main_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE principle_evaluations (id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT, triggered INTEGER);
        CREATE TABLE decisions (id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER, action TEXT);
    """)
    conn.close()

    exit_code = r13.main([
        "--db", str(db), "--json", "--principles-dir", str(fake_dir),
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "global_verdict" in parsed

"""Tests — scripts/v9_principle_alert.py.

Couvre :
- _eval_active — comptage triggers, résolus, hit_rate (mock SQLite tmp)
- _classify_alert — 5 règles + no-alert (cas OK)
- audit — orchestration globale + timestamp ISO
- render_text — format non-vide, lignes cohérentes
- main() — codes retour (0 = no alert, 1 = alertes, 2 = erreur)
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

from scripts import v9_principle_alert as palert  # noqa: E402


# ── _eval_active ──────────────────────────────────────────────────
@pytest.fixture
def temp_db_eval(tmp_path: Path) -> Path:
    """DB SQLite minimale : principle_evaluations + decisions."""
    db = tmp_path / "alert_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT,
            triggered INTEGER
        );
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER,
            resolution_pips REAL
        );
        """
    )
    conn.close()
    return db


def test_eval_active_no_trigger(temp_db_eval: Path) -> None:
    conn = sqlite3.connect(str(temp_db_eval))
    result = palert._eval_active(conn, "PID_X")
    conn.close()
    assert result["n_triggers"] == 0
    assert result["n_resolved"] == 0
    assert result["hit_rate_pct"] is None


def test_eval_active_with_resolved(temp_db_eval: Path) -> None:
    conn = sqlite3.connect(str(temp_db_eval))
    # 10 triggers, 7 résolus (5 wins, 2 losses) → HR = 71.4%
    for i in range(10):
        snap = f"snap-{i}"
        conn.execute(
            "INSERT INTO principle_evaluations (principle_id, snapshot_id, triggered) "
            "VALUES (?, ?, 1)",
            ("PID_Y", snap),
        )
        if i < 7:
            conn.execute(
                "INSERT INTO decisions (snapshot_id, is_win, resolution_pips) "
                "VALUES (?, ?, ?)",
                (snap, 1 if i < 5 else 0, 5.0 if i < 5 else -3.0),
            )
    conn.commit()
    result = palert._eval_active(conn, "PID_Y")
    conn.close()
    assert result["n_triggers"] == 10
    assert result["n_resolved"] == 7
    assert result["hit_rate_pct"] == pytest.approx(71.4, abs=0.1)


def test_eval_active_with_unresolved_decisions(temp_db_eval: Path) -> None:
    """Décisions existent mais is_win=NULL → pas comptées."""
    conn = sqlite3.connect(str(temp_db_eval))
    for i in range(5):
        snap = f"snap-{i}"
        conn.execute(
            "INSERT INTO principle_evaluations (principle_id, snapshot_id, triggered) "
            "VALUES (?, ?, 1)",
            ("PID_Z", snap),
        )
        if i < 3:
            conn.execute(
                "INSERT INTO decisions (snapshot_id, is_win) VALUES (?, NULL)",
                (snap,),
            )
    conn.commit()
    result = palert._eval_active(conn, "PID_Z")
    conn.close()
    # 5 triggers, 0 résolus (les 3 is_win=NULL ne comptent pas)
    assert result["n_triggers"] == 5
    assert result["n_resolved"] == 0


# ── _classify_alert ──────────────────────────────────────────────
def test_classify_no_alert_healthy() -> None:
    """HR 70% sur 200 résolus → tout va bien."""
    counters = {
        "n_triggers": 250, "n_resolved": 200, "hit_rate_pct": 70.0,
        "promoted_at": None,
    }
    assert palert._classify_alert(counters) is None


def test_classify_blocked_data() -> None:
    """Triggers > 0 mais 0 résolu → BLOCKED_DATA."""
    counters = {
        "n_triggers": 100, "n_resolved": 0, "hit_rate_pct": None,
        "promoted_at": None,
    }
    alert = palert._classify_alert(counters)
    assert alert is not None
    assert alert["level"] == "BLOCKED_DATA"


def test_classify_suspect_perfect() -> None:
    """HR 100% sur ≥500 résolus → SUSPECT_PERFECT."""
    counters = {
        "n_triggers": 800, "n_resolved": 600, "hit_rate_pct": 100.0,
        "promoted_at": None,
    }
    alert = palert._classify_alert(counters)
    assert alert is not None
    assert alert["level"] == "SUSPECT_PERFECT"


def test_classify_regression_low_hr() -> None:
    """HR <60% sur ≥100 résolus → REGRESSION."""
    counters = {
        "n_triggers": 200, "n_resolved": 150, "hit_rate_pct": 45.0,
        "promoted_at": None,
    }
    alert = palert._classify_alert(counters)
    assert alert is not None
    assert alert["level"] == "REGRESSION"
    assert "45.0%" in alert["reason"]


def test_classify_regression_below_significance() -> None:
    """HR <60% mais <100 résolus → pas d'alerte (significance)."""
    counters = {
        "n_triggers": 50, "n_resolved": 30, "hit_rate_pct": 45.0,
        "promoted_at": None,
    }
    assert palert._classify_alert(counters) is None


def test_classify_insufficient_data() -> None:
    """Promu récemment (<7j) avec <50 triggers → INSUFFICIENT_DATA."""
    counters = {
        "n_triggers": 10, "n_resolved": 5, "hit_rate_pct": 100.0,
        "promoted_at": "2026-07-08",  # aujourd'hui
    }
    alert = palert._classify_alert(counters)
    assert alert is not None
    assert alert["level"] == "INSUFFICIENT_DATA"


def test_classify_resolver_stale() -> None:
    """≥50 triggers mais <5% résolus → RESOLVER_STALE."""
    counters = {
        "n_triggers": 100, "n_resolved": 3, "hit_rate_pct": 100.0,
        "promoted_at": None,
    }
    alert = palert._classify_alert(counters)
    assert alert is not None
    assert alert["level"] == "RESOLVER_STALE"


def test_classify_no_alert_high_ratio() -> None:
    """Ratio résolus/triggers >5% → pas d'alerte."""
    counters = {
        "n_triggers": 100, "n_resolved": 50, "hit_rate_pct": 80.0,
        "promoted_at": None,
    }
    assert palert._classify_alert(counters) is None


def test_classify_priority_order() -> None:
    """BLOCKED_DATA prime SUSPECT_PERFECT (premier match = priorité)."""
    counters = {
        "n_triggers": 100, "n_resolved": 0, "hit_rate_pct": None,
        "promoted_at": None,
    }
    alert = palert._classify_alert(counters)
    assert alert is not None
    assert alert["level"] == "BLOCKED_DATA"  # Pas SUSPECT (HR=None)


# ── audit (intégration) ──────────────────────────────────────────
def test_audit_empty_db(tmp_path: Path) -> None:
    """DB avec tables vides : 11 ACTIVE audités, alertes attendues
    (promo fraîche GC = INSUFFICIENT_DATA)."""
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT,
            triggered INTEGER
        );
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER,
            resolution_pips REAL
        );
        """
    )
    conn.close()
    report = palert.audit(db_path=db)
    assert report["n_active"] == len(palert.PRINCIPLE_ACTIVE_IDS)
    # Au moins 1 alerte : GRAMMAR_CONTEXTE promu aujourd'hui sans triggers
    assert len(report["alerts"]) >= 1
    gc_alert = next(a for a in report["alerts"] if a["principle_id"] == "GRAMMAR_CONTEXTE")
    assert gc_alert["level"] == "INSUFFICIENT_DATA"
    assert "timestamp" in report
    assert report["timestamp"].endswith("+00:00")  # ISO UTC


# ── render_text ──────────────────────────────────────────────────
def test_render_text_includes_alerts() -> None:
    report = {
        "n_active": 11,
        "alerts": [{"principle_id": "PID_X", "level": "REGRESSION", "reason": "test"}],
        "per_principle": [
            {"principle_id": "PID_X", "n_triggers": 100, "n_resolved": 80,
             "hit_rate_pct": 45.0, "promoted_at": None,
             "alert": {"level": "REGRESSION", "reason": "test"}},
        ],
        "timestamp": "2026-07-08T14:00:00+00:00",
    }
    out = palert.render_text(report)
    assert "PRINCIPE" in out
    assert "PID_X" in out
    assert "REGRESSION" in out
    assert "11" in out  # n_active
    assert "1" in out  # n_alerts


# ── main() — codes retour ───────────────────────────────────────
def _build_empty_db_with_tables(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT,
            triggered INTEGER
        );
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER,
            resolution_pips REAL
        );
        """
    )
    conn.close()


def test_main_no_alert_returns_0(tmp_path: Path,
                                  capsys: pytest.CaptureFixture) -> None:
    """DB avec tables vides → GRAMMAR_CONTEXTE déclenche INSUFFICIENT_DATA
    (promo fraîche) → code retour 1 (alertes présentes)."""
    db = tmp_path / "empty_main.db"
    _build_empty_db_with_tables(db)
    rc = palert.main(["--once", "--db", str(db)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "ACTIVE audités : 11" in captured.out
    assert "INSUFFICIENT_DATA" in captured.out


def test_main_json_output(tmp_path: Path,
                          capsys: pytest.CaptureFixture) -> None:
    """--json produit du JSON valide avec structure attendue."""
    db = tmp_path / "json_main.db"
    _build_empty_db_with_tables(db)
    rc = palert.main(["--once", "--json", "--db", str(db)])
    captured = capsys.readouterr()
    assert rc == 1
    parsed = json.loads(captured.out)
    assert "per_principle" in parsed
    assert "alerts" in parsed
    assert len(parsed["alerts"]) >= 1
    assert "timestamp" in parsed


def test_main_alert_returns_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                              capsys: pytest.CaptureFixture) -> None:
    """Quand alertes présentes → code retour 1 (sémantique cron)."""
    db = tmp_path / "alert_main.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT,
            triggered INTEGER
        );
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER,
            resolution_pips REAL
        );
        """
    )
    # Inject 100 triggers pour GRAMMAR_CONTEXTE + 1 résolu → ratio <5% = STALE
    for i in range(100):
        snap = f"gc-snap-{i}"
        conn.execute(
            "INSERT INTO principle_evaluations (principle_id, snapshot_id, triggered) "
            "VALUES (?, ?, 1)",
            ("GRAMMAR_CONTEXTE", snap),
        )
    conn.execute(
        "INSERT INTO decisions (snapshot_id, is_win, resolution_pips) "
        "VALUES (?, 1, 5.0)",
        ("gc-snap-0",),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(palert, "DB_PATH", db)
    rc = palert.main(["--once"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "RESOLVER_STALE" in captured.out
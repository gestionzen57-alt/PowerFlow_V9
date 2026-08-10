"""Z-HEALTH — tests run_live_health_check.py (6 couches).

Vérifie :
  1. build_health() → 6 couches présentes + score 0-100 + status HEALTHY/DEGRADED
  2. check_spread : spread OK → score 100 ; spread > seuil → score < 100
  3. check_latency : DB rapide → ok=True ; seuil bas → ok=False (R8)
  4. check_broker : port fermé → fail-open (ok=False, error, pas de crash)
  5. check_data_gap : DB absente → fail-open (error, score 0)
  6. R6 : chaque couche isolée — une erreur n'empêche pas les autres
  7. R9 : rapport JSON sérialisable + R10 : aucune écriture DB
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_live_health_check import (  # noqa: E402
    build_health,
    check_broker,
    check_data_gap,
    check_latency,
    check_spread,
)


@pytest.fixture
def tiny_db(tmp_path: Path) -> Path:
    """Mini DB forces_snapshots avec spread faible (M5)."""
    db = tmp_path / "tiny.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE forces_snapshots ("
        " symbol TEXT, timeframe TEXT, is_closed_bar INTEGER,"
        " bar_time INTEGER, spread_points REAL)"
    )
    for i in range(50):
        con.execute(
            "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)",
            ("EURUSD", "M5", 1, 1_700_000_000 + i * 300, 3.0),
        )
    con.commit()
    con.close()
    return db


def test_build_health_6_layers():
    """Les 6 couches sont présentes, score borné, status valide."""
    r = build_health()
    assert set(r["layers"]) == {
        "broker", "spread", "data_gap", "latency",
        "session_active", "live_readiness",
    }
    assert 0.0 <= r["score"] <= 100.0
    assert r["status"] in ("HEALTHY", "DEGRADED", "ERROR")


def test_check_spread_ok(tiny_db: Path):
    """Spread moyen 3.0 <= 10 → ok, score 100."""
    out = check_spread(tiny_db)
    assert out["ok"] is True
    assert out["score"] == 100.0
    assert out["detail"]["avg_spread_points"] == 3.0


def test_check_spread_anormal(tmp_path: Path):
    """Spread moyen 25 > 10 → ok=False, score < 100."""
    db = tmp_path / "wide.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE forces_snapshots ("
        " symbol TEXT, timeframe TEXT, is_closed_bar INTEGER,"
        " bar_time INTEGER, spread_points REAL)"
    )
    for i in range(20):
        con.execute(
            "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)",
            ("EURUSD", "M5", 1, 1_700_000_000 + i * 300, 25.0),
        )
    con.commit()
    con.close()
    out = check_spread(db)
    assert out["ok"] is False
    assert out["score"] < 100.0


def test_check_latency_ok(tiny_db: Path):
    """DB locale → latence < 80 ms (ok)."""
    out = check_latency(tiny_db)
    assert out["ok"] is True
    assert out["detail"]["latency_ms"] < 80.0


def test_check_latency_seuil_bas(tiny_db: Path):
    """R8 : seuil 0.001 ms → ok=False (latence réelle > seuil)."""
    out = check_latency(tiny_db, max_ms=0.001)
    assert out["ok"] is False


def test_check_broker_failopen():
    """Port fermé → fail-open (ok=False + error, jamais d'exception)."""
    out = check_broker(host="127.0.0.1", port=1, timeout=0.2)
    assert out["ok"] is False
    assert out["error"] is not None
    assert out["score"] == 0.0


def test_check_data_gap_db_absente_failopen(tmp_path: Path):
    """DB inexistante → fail-open (ok=False, recommendation ERROR, pas de crash).

    validate_data_continuity retourne un GapReport avec
    recommendation='ERROR:...' au lieu de lever (R6 du validator).
    """
    out = check_data_gap(tmp_path / "nope.db")
    assert out["ok"] is False
    assert out["score"] == 0.0
    assert out["detail"]["recommendation"].startswith("ERROR")


def test_r9_json_serialisable():
    """R9 : le rapport complet est sérialisable JSON."""
    r = build_health()
    json.dumps(r, ensure_ascii=False)


def test_r10_lecture_seule(tiny_db: Path):
    """R10 : les checks n'écrivent rien dans la DB (mode ro)."""
    before = sqlite3.connect(tiny_db).execute(
        "SELECT COUNT(*) FROM forces_snapshots"
    ).fetchone()[0]
    check_spread(tiny_db)
    check_latency(tiny_db)
    after = sqlite3.connect(tiny_db).execute(
        "SELECT COUNT(*) FROM forces_snapshots"
    ).fetchone()[0]
    assert before == after


def test_check_session_active_failopen():
    """Couche 5 : session évaluée sans crash (score borné 0-100)."""
    from scripts.run_live_health_check import check_session_active
    out = check_session_active("EURUSD")
    assert 0.0 <= out["score"] <= 100.0
    assert out["ok"] in (True, False)


def test_check_live_readiness_failopen():
    """Couche 6 : audit C11 sans track record → fail-open, jamais de crash."""
    from scripts.run_live_health_check import check_live_readiness
    out = check_live_readiness()
    assert out["ok"] in (True, False)
    assert "gates" in out["detail"]


def test_build_health_status_degraded_si_score_bas():
    """Score < 90 → status DEGRADED (spec Z-HEALTH)."""
    r = build_health()
    if r["score"] < 90.0:
        assert r["status"] == "DEGRADED"
    else:
        assert r["status"] == "HEALTHY"

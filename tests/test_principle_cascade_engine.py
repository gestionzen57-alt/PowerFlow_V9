"""Tests — PrincipleCascadeEngine (Couche 4 combinaisons) PowerFlow V9."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.v9.db_schema import get_connection
from core.v9.decision_db import init_decision_db
from core.v9.principle_db import init_principle_db
from core.v9.principle_cascade_engine import (
    PrincipleCascadeEngine,
    init_cascade_db,
    make_cascade_id,
)


def _snap(conn, sid: str, principles: list[str], is_win: int, pips: float) -> None:
    ts = "2026-07-10T03:30:00+00:00"
    for pid in principles:
        conn.execute(
            "INSERT INTO principle_evaluations (evaluation_id, snapshot_id, "
            "principle_id, triggered, direction, timeframe, timestamp) "
            "VALUES (?,?,?,?,?,?,?)",
            (f"ev-{sid}-{pid}", sid, pid, 1, "haussiere", "M5", ts),
        )
    conn.execute(
        "INSERT INTO decisions (decision_id, snapshot_id, action, direction, "
        "timeframe, regime_type, timestamp, is_win, resolution_pips) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (f"dec-{sid}", sid, "preparer_entree", "haussiere", "M5", "CASSURE",
         ts, is_win, pips),
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_cascade_test.db"
    init_principle_db(path)
    init_decision_db(path)
    init_cascade_db(path)
    return path


def _seed_booster(conn) -> None:
    """A+B ensemble = 90% ; A seul et B seul ≈ 20%."""
    i = 0
    for _ in range(30):  # combo A+B, 90% win
        _snap(conn, f"c{i}", ["A", "B"], 1 if i % 10 != 0 else 0, 5.0)
        i += 1
    for _ in range(30):  # A seul, 20% win
        _snap(conn, f"a{i}", ["A"], 1 if i % 5 == 0 else 0, -3.0)
        i += 1
    for _ in range(30):  # B seul, 20% win
        _snap(conn, f"b{i}", ["B"], 1 if i % 5 == 0 else 0, -3.0)
        i += 1


def test_discover_cascades(db_path: Path) -> None:
    conn = get_connection(db_path)
    _seed_booster(conn)
    conn.commit()
    conn.close()

    eng = PrincipleCascadeEngine(db_path=db_path)
    cascades = eng.discover_cascades(min_n=20, min_wr_lift=5.0)

    ab = next((c for c in cascades if c["cascade_id"] == make_cascade_id(["A", "B"])), None)
    assert ab is not None
    assert ab["kind"] == "booster"
    assert ab["win_rate"] == 90.0
    assert ab["wr_lift"] > 5.0
    assert ab["n_trades"] == 30


def test_score_cascade(db_path: Path) -> None:
    conn = get_connection(db_path)
    _seed_booster(conn)
    conn.commit()
    conn.close()

    eng = PrincipleCascadeEngine(db_path=db_path)
    score = eng.score_cascade(["A", "B"])
    assert score["n_trades"] == 30
    assert score["win_rate"] == 90.0
    assert score["wr_lift"] > 0
    assert score["confidence_boost"] > 0


def test_apply_cascade_confidence_boost() -> None:
    eng = PrincipleCascadeEngine.__new__(PrincipleCascadeEngine)  # sans DB
    arbiter_result = {"direction": "haussiere", "confiance_arbitree": 60.0}
    cascades = [{"cascade_id": "A+B", "principles": ["A", "B"], "wr_lift": 30.0}]

    boosted = eng.apply_cascade_confidence_boost(arbiter_result, cascades)
    assert boosted["cascade_boost"] == 15.0  # 30 * 0.5
    assert boosted["confiance_arbitree_boosted"] == 75.0
    assert boosted["cascade_source"] == "A+B"
    # Non destructif : l'original garde sa confiance
    assert arbiter_result["confiance_arbitree"] == 60.0

    # Cap à 100
    high = eng.apply_cascade_confidence_boost(
        {"confiance_arbitree": 95.0}, cascades)
    assert high["confiance_arbitree_boosted"] == 100.0

    # Sans cascade → boost nul
    none = eng.apply_cascade_confidence_boost({"confiance_arbitree": 60.0}, [])
    assert none["cascade_boost"] == 0.0
    assert none["confiance_arbitree_boosted"] == 60.0


def test_active_and_snapshot_match(db_path: Path) -> None:
    conn = get_connection(db_path)
    _seed_booster(conn)
    conn.commit()
    conn.close()

    eng = PrincipleCascadeEngine(db_path=db_path)
    eng.discover_cascades(min_n=20, min_wr_lift=5.0)  # persiste dans le registre

    active = eng.get_active_cascades(min_wr_lift=5.0)
    assert any(c["cascade_id"] == make_cascade_id(["A", "B"]) for c in active)

    # Le snapshot combo c0 (A+B triggered) doit matcher la cascade active
    matched = eng.get_cascade_for_snapshot("c0", active)
    assert any(c["cascade_id"] == make_cascade_id(["A", "B"]) for c in matched)

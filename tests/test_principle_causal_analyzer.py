"""Tests — PrincipleCausalAnalyzer (Couche 3 recherche causale) PowerFlow V9."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.v9.db_schema import get_connection, init_db
from core.v9.decision_db import init_decision_db
from core.v9.principle_db import init_principle_db
from core.v9.regime_db import init_regime_db
from core.v9.principle_causal_analyzer import (
    PrincipleCausalAnalyzer,
    generate_hypothesis,
    init_causal_db,
)


def _insert(
    conn,
    sid: str,
    is_win: int,
    pips: float,
    *,
    hour: int,
    spread: float,
    principle_id: str = "TEST_P",
    regime: str = "CASSURE",
) -> None:
    ts = f"2026-07-10T{hour:02d}:30:00+00:00"
    conn.execute(
        "INSERT INTO forces_snapshots (snapshot_id, spread_price) VALUES (?,?)",
        (sid, spread),
    )
    conn.execute(
        "INSERT INTO principle_evaluations (evaluation_id, snapshot_id, "
        "principle_id, triggered, direction, timeframe, timestamp) "
        "VALUES (?,?,?,?,?,?,?)",
        (f"ev-{sid}", sid, principle_id, 1, "haussiere", "M5", ts),
    )
    conn.execute(
        "INSERT INTO decisions (decision_id, snapshot_id, action, direction, "
        "timeframe, regime_type, timestamp, is_win, resolution_pips) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (f"dec-{sid}", sid, "preparer_entree", "haussiere", "M5", regime, ts,
         is_win, pips),
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_causal_test.db"
    init_db(path)
    init_principle_db(path)
    init_decision_db(path)
    init_regime_db(path)
    init_causal_db(path)
    return path


def test_analyze_underperformance(db_path: Path) -> None:
    """London (spread élevé, tous perdants) vs Asie (spread bas, gagnants).

    L'analyse doit détecter le WR effondré + un facteur défavorable (spread ou
    faux signaux) et produire une hypothèse textuelle."""
    conn = get_connection(db_path)
    # Asie : 30 trades, spread bas 0.0001, 90% gagnants
    for i in range(30):
        win = 1 if i % 10 != 0 else 0
        _insert(conn, f"a{i}", win, 6.0 if win else -6.0, hour=3, spread=0.0001)
    # London : 20 trades, spread élevé 0.0006, tous perdants
    for i in range(20):
        _insert(conn, f"l{i}", 0, -8.0, hour=9, spread=0.0006)
    conn.commit()
    conn.close()

    an = PrincipleCausalAnalyzer(db_path=db_path)
    res = an.analyze_underperformance("TEST_P", "session", "london")

    assert res["value"] == "london"
    assert res["wr_delta"] < -15.0  # WR bien en-dessous du global
    assert res["n_trades"] == 20
    # spread ou faux signaux doivent ressortir comme facteurs défavorables
    factor_names = {f["factor"] for f in res["worse_factors"]}
    assert factor_names & {"spread_price", "false_signal_rate"}
    assert isinstance(res["hypothesis"], str)
    assert "london" in res["hypothesis"]

    # Journal alimenté
    journal = an.get_journal("TEST_P")
    assert len(journal) >= 1
    assert journal[0]["dimension"] == "session"


def test_analyze_session_loss(db_path: Path) -> None:
    """analyze_session_loss délègue à analyze_underperformance sur la session."""
    conn = get_connection(db_path)
    for i in range(20):
        _insert(conn, f"a{i}", 1, 5.0, hour=3, spread=0.0001)
    for i in range(15):
        _insert(conn, f"n{i}", 0, -10.0, hour=18, spread=0.0005)  # new_york
    conn.commit()
    conn.close()

    an = PrincipleCausalAnalyzer(db_path=db_path)
    res = an.analyze_session_loss("TEST_P", "new_york")
    assert res["dimension"] == "session"
    assert res["value"] == "new_york"
    assert res["target_wr"] == 0.0


def test_generate_hypothesis() -> None:
    """Format d'hypothèse : mentionne le principe, la dimension, la cause."""
    obs = {
        "principle_id": "PRICE_LAG_AT_NODE_BIRTH",
        "dimension": "session",
        "value": "new_york",
        "worse_factors": [
            {"factor": "spread_price", "ratio": 0.85},
            {"factor": "false_signal_rate", "ratio": 0.50},
        ],
    }
    h = generate_hypothesis(obs)
    assert "PRICE_LAG_AT_NODE_BIRTH" in h
    assert "new_york" in h
    assert "spread" in h.lower()

    # Sans facteur → hypothèse « bruit »
    obs_empty = {"principle_id": "X", "dimension": "regime", "value": "NEUTRE",
                 "worse_factors": []}
    h2 = generate_hypothesis(obs_empty)
    assert "X" in h2


def test_validate_hypothesis(db_path: Path) -> None:
    """Validation : facteurs défavorables confirmés → validée."""
    conn = get_connection(db_path)
    for i in range(30):
        _insert(conn, f"a{i}", 1, 6.0, hour=3, spread=0.0001)
    for i in range(20):
        _insert(conn, f"l{i}", 0, -8.0, hour=9, spread=0.0008)
    conn.commit()
    conn.close()

    an = PrincipleCausalAnalyzer(db_path=db_path)
    res = an.validate_hypothesis(
        "TEST_P", "spread trop élevé en london", "session", "london",
    )
    assert res["validated"] is True
    journal = an.get_journal("TEST_P")
    assert any(j["status"] == "validated" for j in journal)

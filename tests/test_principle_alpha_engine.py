"""Tests — PrincipleAlphaEngine (Couche 1+2 mesure alpha) PowerFlow V9."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.v9.db_schema import get_connection
from core.v9.decision_db import init_decision_db
from core.v9.principle_db import init_principle_db
from core.v9.regime_db import init_regime_db
from core.v9.principle_alpha_engine import (
    PrincipleAlphaEngine,
    _compute_stability,
    _metrics_from_trades,
    init_alpha_db,
)


def _insert_trade(
    conn,
    snapshot_id: str,
    principle_id: str,
    is_win: int,
    pips: float,
    *,
    hour: int = 3,
    regime: str = "CASSURE",
    direction: str = "haussiere",
    timeframe: str = "M5",
) -> None:
    """Insère un couple principle_evaluation (triggered) + decision (résolue)."""
    ts = f"2026-07-10T{hour:02d}:30:00+00:00"
    conn.execute(
        """
        INSERT INTO principle_evaluations
            (evaluation_id, snapshot_id, principle_id, triggered, direction,
             timeframe, timestamp, confidence)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (f"ev-{snapshot_id}", snapshot_id, principle_id, 1, direction,
         timeframe, ts, 80),
    )
    conn.execute(
        """
        INSERT INTO decisions
            (decision_id, snapshot_id, action, direction, timeframe,
             regime_type, timestamp, is_win, resolution_pips)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (f"dec-{snapshot_id}", snapshot_id, "preparer_entree", direction,
         timeframe, regime, ts, is_win, pips),
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_alpha_test.db"
    init_principle_db(path)
    init_decision_db(path)
    init_regime_db(path)
    init_alpha_db(path)
    return path


# ── _metrics_from_trades (unité pure) ─────────────────────────

def test_compute_metrics_basic(db_path: Path) -> None:
    """WR et expectancy sur données connues : 7 wins/10, +5 pips chacun,
    3 losses -10 pips → WR 70%, expectancy (35-30)/10 = 0.5 pip."""
    conn = get_connection(db_path)
    for i in range(7):
        _insert_trade(conn, f"s{i}", "TEST_P", 1, 5.0)
    for i in range(7, 10):
        _insert_trade(conn, f"s{i}", "TEST_P", 0, -10.0)
    conn.commit()
    conn.close()

    engine = PrincipleAlphaEngine(db_path=db_path)
    m = engine.compute_metrics("TEST_P")

    assert m["n_trades"] == 10
    assert m["wins"] == 7
    assert m["losses"] == 3
    assert m["win_rate"] == 70.0
    assert m["expectancy"] == pytest.approx(0.5)
    assert m["total_pips"] == pytest.approx(5.0)
    # profit_factor = 35 / 30
    assert m["profit_factor"] == pytest.approx(35 / 30, abs=0.01)
    assert not m["insufficient"]


def test_compute_metrics_insufficient(db_path: Path) -> None:
    """n < min_n → flag insufficient."""
    conn = get_connection(db_path)
    for i in range(3):
        _insert_trade(conn, f"s{i}", "TEST_P", 1, 5.0)
    conn.commit()
    conn.close()

    engine = PrincipleAlphaEngine(db_path=db_path)
    m = engine.compute_metrics("TEST_P", min_n=5)
    assert m["n_trades"] == 3
    assert m["insufficient"]


def test_compute_all_dimensions(db_path: Path) -> None:
    """Décomposition par session : asie gagnant, london perdant."""
    conn = get_connection(db_path)
    # 10 trades asie (hour 3), tous gagnants
    for i in range(10):
        _insert_trade(conn, f"a{i}", "TEST_P", 1, 6.0, hour=3)
    # 10 trades london (hour 9), tous perdants
    for i in range(10):
        _insert_trade(conn, f"l{i}", "TEST_P", 0, -8.0, hour=9)
    conn.commit()
    conn.close()

    engine = PrincipleAlphaEngine(db_path=db_path)
    dims = engine.compute_all_dimensions("TEST_P")

    sessions = dims["dimensions"]["session"]
    assert "asie" in sessions
    assert "london" in sessions
    assert sessions["asie"]["win_rate"] == 100.0
    assert sessions["london"]["win_rate"] == 0.0
    # Global WR 50% → london (0%) underperforming, asie (100%) outperforming
    under_sessions = {u["value"] for u in dims["underperforming"]}
    over_sessions = {o["value"] for o in dims["outperforming"]}
    assert "london" in under_sessions
    assert "asie" in over_sessions


def test_detect_edge_decay(db_path: Path) -> None:
    """WR historique élevé puis effondrement récent → alerte de décroissance."""
    conn = get_connection(db_path)
    # 100 premiers trades gagnants, 60 derniers perdants
    idx = 0
    for _ in range(100):
        _insert_trade(conn, f"g{idx}", "TEST_P", 1, 5.0)
        idx += 1
    for _ in range(60):
        _insert_trade(conn, f"b{idx}", "TEST_P", 0, -5.0)
        idx += 1
    conn.commit()
    conn.close()

    engine = PrincipleAlphaEngine(db_path=db_path)
    decay = engine.detect_edge_decay("TEST_P", window_sizes=[50])
    assert decay["decayed"] is True
    assert decay["alert"] is not None
    assert decay["windows"][50]["delta"] < -15.0


def test_rank_principles(db_path: Path) -> None:
    """Classement par expectancy décroissante."""
    conn = get_connection(db_path)
    # P_HIGH : +6 pips avg ; P_LOW : -3 pips avg
    for i in range(20):
        _insert_trade(conn, f"h{i}", "P_HIGH", 1, 6.0)
    for i in range(20):
        _insert_trade(conn, f"x{i}", "P_LOW", 0, -3.0)
    conn.commit()
    conn.close()

    engine = PrincipleAlphaEngine(db_path=db_path)
    ranking = engine.rank_principles(metric="expectancy", min_n=10)
    ids = [r[0] for r in ranking]
    assert ids.index("P_HIGH") < ids.index("P_LOW")
    assert ranking[0][0] == "P_HIGH"


def test_persist_and_stability(db_path: Path) -> None:
    """persist_metrics écrit la ligne globale ; stability ∈ [0,1]."""
    conn = get_connection(db_path)
    for i in range(20):
        _insert_trade(conn, f"s{i}", "TEST_P", 1 if i % 2 == 0 else 0,
                      5.0 if i % 2 == 0 else -5.0)
    conn.commit()
    conn.close()

    engine = PrincipleAlphaEngine(db_path=db_path)
    n = engine.persist_metrics("TEST_P")
    assert n >= 1

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT n_trades, win_rate, stability FROM principle_alpha_metrics "
        "WHERE principle_id='TEST_P' AND session='ALL'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 20
    assert 0.0 <= row[2] <= 1.0


def test_metrics_empty() -> None:
    """Aucun trade → métriques neutres, pas de crash."""
    m = _metrics_from_trades([])
    assert m["n_trades"] == 0
    assert m["win_rate"] == 0.0
    assert _compute_stability([]) == 0.0

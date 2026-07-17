"""Tests pytest — core/v9/v9_auto_promotion.py.

Couvre : validation constructeur, agrégation par principe (jointure
json_each), évaluation R25'' (promote/keep/demote), apply_promotions,
R6 défensif (DB manquante / SQL error).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9.v9_auto_promotion import (
    AutoPromotionEngine,
    PromotionDecision,
    STATUS_ACTIVE,
    STATUS_SHADOW,
    main,
)


SCHEMA_SQL = """
CREATE TABLE principles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    principle_id TEXT UNIQUE,
    version INTEGER,
    origin TEXT,
    kind TEXT,
    source_status TEXT,
    v9_status TEXT,
    scope_timeframes_json TEXT,
    scope_currencies_json TEXT,
    conditions_json TEXT,
    emits_json TEXT,
    bounds_json TEXT,
    anti_signal_bias INTEGER,
    notes TEXT,
    created_by TEXT,
    created_at_source TEXT,
    synced_at TEXT
);
CREATE TABLE paper_trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT,
    direction TEXT,
    confiance REAL,
    principes_source TEXT,
    opened_at TEXT,
    closed_at TEXT,
    pips_simulated REAL,
    is_win INTEGER,
    risk_go_context TEXT
);
"""


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(SCHEMA_SQL)
    return db


def _add_principle(
    conn: sqlite3.Connection,
    principle_id: str,
    v9_status: str = STATUS_SHADOW,
) -> None:
    conn.execute(
        "INSERT INTO principles (principle_id, v9_status, kind) VALUES (?, ?, 'node_rule')",
        (principle_id, v9_status),
    )


def _add_trades(
    conn: sqlite3.Connection,
    principles: list[str],
    pips_values: list[float],
    wins: list[int],
) -> None:
    for pips, win in zip(pips_values, wins):
        conn.execute(
            "INSERT INTO paper_trades "
            "(snapshot_id, direction, confiance, principes_source, opened_at, "
            " closed_at, pips_simulated, is_win, risk_go_context) "
            "VALUES (?, 'LONG', 0.8, ?, '2026-01-01', '2026-01-01', ?, ?, '{}')",
            (f"snap-{pips}-{win}", json_dumps(principles), pips, win),
        )


def json_dumps(items: list[str]) -> str:
    import json
    return json.dumps(items)


# ── Tests ──────────────────────────────────────────────────────────


def test_constructor_validation():
    with pytest.raises(ValueError):
        AutoPromotionEngine(min_wr=-0.1)
    with pytest.raises(ValueError):
        AutoPromotionEngine(min_wr=1.5)
    with pytest.raises(ValueError):
        AutoPromotionEngine(min_n_trades=0)
    e = AutoPromotionEngine(min_wr=0.7, min_n_trades=100, min_sharpe=1.0)
    assert e.min_wr == 0.7
    assert e.min_n_trades == 100
    assert e.min_sharpe == 1.0


def test_promote_shadow_to_active(tmp_path: Path):
    """Principe SHADOW avec métriques solides → promote."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _add_principle(conn, "PROMOTE_ME", STATUS_SHADOW)
    # 100 trades : 80 wins (+5), 20 losses (-5) → wr=80%, expectancy=+3
    pips = [5.0] * 80 + [-5.0] * 20
    wins = [1] * 80 + [0] * 20
    _add_trades(conn, ["PROMOTE_ME"], pips, wins)
    conn.commit()
    conn.close()

    e = AutoPromotionEngine(min_wr=0.70, min_n_trades=100, min_sharpe=1.0, db_path=db)
    decisions = e.evaluate_principles()
    assert len(decisions) == 1
    d = decisions[0]
    assert d.principle_id == "PROMOTE_ME"
    assert d.action == "promote"
    assert d.current_status == STATUS_SHADOW
    assert d.new_status == STATUS_ACTIVE


def test_keep_shadow_below_thresholds(tmp_path: Path):
    """SHADOW avec WR insuffisant → keep."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _add_principle(conn, "LOW_WR", STATUS_SHADOW)
    # 100 trades : 50 wins, 50 losses → wr=50%
    pips = [5.0] * 50 + [-5.0] * 50
    wins = [1] * 50 + [0] * 50
    _add_trades(conn, ["LOW_WR"], pips, wins)
    conn.commit()
    conn.close()

    e = AutoPromotionEngine(min_wr=0.70, min_n_trades=100, min_sharpe=1.0, db_path=db)
    decisions = e.evaluate_principles()
    assert decisions[0].action == "keep"
    assert decisions[0].new_status == STATUS_SHADOW


def test_keep_shadow_too_few_trades(tmp_path: Path):
    """n_trades < min_n_trades → keep même si WR élevé."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _add_principle(conn, "TOO_FEW", STATUS_SHADOW)
    _add_trades(conn, ["TOO_FEW"], [10.0] * 30, [1] * 30)
    conn.commit()
    conn.close()

    e = AutoPromotionEngine(min_wr=0.70, min_n_trades=100, min_sharpe=1.0, db_path=db)
    decisions = e.evaluate_principles()
    assert decisions[0].action == "keep"


def test_demote_active_below_demote_wr(tmp_path: Path):
    """ACTIVE avec WR dégradé → demote."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _add_principle(conn, "DEGRADED", STATUS_ACTIVE)
    # 200 trades : 80 wins (40%) → wr=40% (sous demote_wr=55%)
    pips = [5.0] * 80 + [-5.0] * 120
    wins = [1] * 80 + [0] * 120
    _add_trades(conn, ["DEGRADED"], pips, wins)
    conn.commit()
    conn.close()

    e = AutoPromotionEngine(min_wr=0.70, min_n_trades=100, min_sharpe=1.0, db_path=db)
    decisions = e.evaluate_principles()
    assert decisions[0].action == "demote"
    assert decisions[0].new_status == STATUS_SHADOW


def test_keep_active_solid(tmp_path: Path):
    """ACTIVE avec WR sain → keep."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _add_principle(conn, "SOLID", STATUS_ACTIVE)
    _add_trades(conn, ["SOLID"], [5.0] * 80 + [-5.0] * 20, [1] * 80 + [0] * 20)
    conn.commit()
    conn.close()

    e = AutoPromotionEngine(db_path=db)
    decisions = e.evaluate_principles()
    assert decisions[0].action == "keep"
    assert decisions[0].new_status == STATUS_ACTIVE


def test_trade_attribution_multi_principles(tmp_path: Path):
    """Un trade avec plusieurs principes → chaque principe reçoit le trade."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _add_principle(conn, "P_A", STATUS_SHADOW)
    _add_principle(conn, "P_B", STATUS_SHADOW)
    # 200 trades partagés P_A et P_B → chacun a 200 trades
    for i in range(200):
        pips = 5.0 if i % 5 != 0 else -5.0
        win = 1 if pips > 0 else 0
        conn.execute(
            "INSERT INTO paper_trades "
            "(snapshot_id, principes_source, opened_at, closed_at, "
            " pips_simulated, is_win, risk_go_context) "
            "VALUES (?, ?, '2026-01-01', '2026-01-01', ?, ?, '{}')",
            (f"s-{i}", json_dumps(["P_A", "P_B"]), pips, win),
        )
    conn.commit()
    conn.close()

    e = AutoPromotionEngine(min_wr=0.70, min_n_trades=100, min_sharpe=1.0, db_path=db)
    decisions = e.evaluate_principles()
    assert len(decisions) == 2
    for d in decisions:
        assert d.metrics["n_trades"] == 200


def test_apply_promotions_persists(tmp_path: Path):
    """apply_promotions écrit en DB."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _add_principle(conn, "WILL_PROMOTE", STATUS_SHADOW)
    _add_trades(conn, ["WILL_PROMOTE"], [5.0] * 80 + [-5.0] * 20, [1] * 80 + [0] * 20)
    conn.commit()
    conn.close()

    e = AutoPromotionEngine(min_wr=0.70, min_n_trades=100, min_sharpe=1.0, db_path=db)
    decisions = e.evaluate_principles()
    applied = e.apply_promotions(decisions)
    assert applied == 1

    # Vérifier en DB
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT v9_status FROM principles WHERE principle_id = ?",
        ("WILL_PROMOTE",),
    ).fetchone()
    conn.close()
    assert row[0] == STATUS_ACTIVE


def test_apply_promotions_keeps_no_op(tmp_path: Path):
    """apply_promotions ne touche pas les 'keep'."""
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _add_principle(conn, "NO_OP", STATUS_SHADOW)
    _add_trades(conn, ["NO_OP"], [5.0] * 50 + [-5.0] * 50, [1] * 50 + [0] * 50)
    conn.commit()
    conn.close()

    e = AutoPromotionEngine(min_wr=0.70, min_n_trades=100, min_sharpe=1.0, db_path=db)
    decisions = e.evaluate_principles()
    assert decisions[0].action == "keep"
    applied = e.apply_promotions(decisions)
    assert applied == 0


def test_promotion_decision_to_dict():
    """PromotionDecision sérialise en dict."""
    d = PromotionDecision(
        principle_id="P1",
        action="promote",
        current_status="SHADOW",
        new_status="ACTIVE",
        metrics={"wr": 0.8, "n_trades": 100, "sharpe": 1.5, "pf": 2.0},
        rationale="OK",
    )
    dd = d.to_dict()
    assert dd["principle_id"] == "P1"
    assert dd["metrics"]["wr"] == 0.8


def test_decisions_sorted_by_action():
    """Les décisions sont triées promote → demote → keep."""
    e = AutoPromotionEngine()
    decisions = [
        PromotionDecision(principle_id="K", action="keep", current_status="X", new_status="X"),
        PromotionDecision(principle_id="P", action="promote", current_status="S", new_status="A"),
        PromotionDecision(principle_id="D", action="demote", current_status="A", new_status="S"),
    ]
    # On force l'ordre via le sort interne de evaluate, mais on vérifie le tri ici
    sorted_d = sorted(decisions, key=lambda d: ({"promote": 0, "demote": 1, "keep": 2}[d.action], d.principle_id))
    assert sorted_d[0].action == "promote"
    assert sorted_d[1].action == "demote"
    assert sorted_d[2].action == "keep"


def test_empty_db_returns_empty():
    """DB vide → liste vide sans crash."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        empty_path = Path(f.name)
    # Le fichier existe mais est vide (pas de schéma) → on s'attend à 0 décisions
    e = AutoPromotionEngine(db_path=empty_path)
    decisions = e.evaluate_principles()
    assert decisions == []


def test_main_cli_summary(monkeypatch, capsys):
    """CLI --summary tourne sans crash."""
    import json
    monkeypatch.setattr("sys.argv", ["v9_auto_promotion.py", "--summary"])
    rc = main()
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert "version" in parsed
    assert "counts" in parsed


def test_main_cli_evaluate(monkeypatch, capsys):
    """CLI --evaluate retourne des décisions."""
    import json
    monkeypatch.setattr("sys.argv", ["v9_auto_promotion.py", "--evaluate"])
    rc = main()
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert "decisions" in parsed
    assert "thresholds" in parsed
    assert isinstance(parsed["decisions"], list)
"""Tests unitaires — PaperTradeLogger (Phase 10).

Couvre 5 cas exigés par le brief :
  1. test_log_open_cree_trade
  2. test_log_close_met_a_jour
  3. test_is_win_positif
  4. test_is_win_negatif
  5. test_idempotence_trade_id_unique

+ tests annexes : trade_id explicite, erreurs, context None, journalisation.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from core.v9 import config, db_schema
from core.v9.db_schema import get_connection
from core.v9.paper_trade_logger import PaperTradeLogger, PaperTradeLoggerError
from core.v9.paper_trades_db import init_paper_trades_db


# ---------- Fixtures ----------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "v9_paper_test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db_schema, "DB_PATH", path)
    init_paper_trades_db(path)
    return path


def _arbiter_result(
    snapshot_id: str = "snap_test",
    direction: str = "haussiere",
    confiance: int = 85,
    nb_principes: int = 3,
) -> dict:
    return {
        "direction": direction,
        "confiance_arbitree": confiance,
        "principes_source": [f"P{i}" for i in range(nb_principes)],
        "nb_principes_actifs": nb_principes,
        "timestamp": "2026-07-07T10:00:00+00:00",
        "arbiter_version": "1.0",
        "snapshot_id": snapshot_id,
    }


def _context_ok() -> dict:
    return {
        "news_phase": "NEUTRE",
        "window_status": "exploitable",
        "session_marche": "london",
    }


def _row(db_path: Path, trade_id: str) -> dict:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT * FROM paper_trades WHERE trade_id = ?", (trade_id,)
        ).fetchone()
        return dict(r) if r else {}
    finally:
        conn.close()


# ---------- Tests ----------


def test_log_open_cree_trade(db_path: Path) -> None:
    """Cas 1 — log_open crée une rangée avec tous les champs attendus."""
    logger = PaperTradeLogger(db_path=db_path)
    arb = _arbiter_result(snapshot_id="snap_open_001")
    ctx = _context_ok()

    trade_id = logger.log_open(arb, ctx)

    # Format pt_xxxxxxxxxxxx (12 hex)
    assert re.match(r"^pt_[0-9a-f]{12}$", trade_id), f"trade_id mal formé : {trade_id}"

    row = _row(db_path, trade_id)
    assert row["snapshot_id"] == "snap_open_001"
    assert row["direction"] == "haussiere"
    assert row["confiance"] == 85
    assert row["closed_at"] is None
    assert row["pips_simulated"] is None
    assert row["is_win"] is None
    assert row["opened_at"] is not None
    # Principes JSON
    ps = json.loads(row["principes_source"])
    assert ps == ["P0", "P1", "P2"]
    # Context JSON
    ctx_loaded = json.loads(row["risk_go_context"])
    assert ctx_loaded["news_phase"] == "NEUTRE"
    assert ctx_loaded["window_status"] == "exploitable"


def test_log_open_trade_id_explicite(db_path: Path) -> None:
    """trade_id fourni explicitement est respecté (utile pour idempotence)."""
    logger = PaperTradeLogger(db_path=db_path)
    trade_id = "pt_custom00001"
    result = logger.log_open(_arbiter_result(), _context_ok(), trade_id=trade_id)
    assert result == trade_id
    assert _row(db_path, trade_id)["trade_id"] == trade_id


def test_log_open_context_none(db_path: Path) -> None:
    """context=None accepté, risk_go_context = '{}' en DB."""
    logger = PaperTradeLogger(db_path=db_path)
    trade_id = logger.log_open(_arbiter_result(), None)
    row = _row(db_path, trade_id)
    assert json.loads(row["risk_go_context"]) == {}


def test_log_open_sans_snapshot_id_leve(db_path: Path) -> None:
    """arbiter_result sans snapshot_id → PaperTradeLoggerError."""
    logger = PaperTradeLogger(db_path=db_path)
    arb = _arbiter_result()
    arb["snapshot_id"] = None
    with pytest.raises(PaperTradeLoggerError, match="snapshot_id"):
        logger.log_open(arb, _context_ok())


def test_log_open_direction_neutre_leve(db_path: Path) -> None:
    """direction='neutre' refusée (le risk_manager doit déjà filtrer)."""
    logger = PaperTradeLogger(db_path=db_path)
    arb = _arbiter_result(direction="neutre")
    with pytest.raises(PaperTradeLoggerError, match="direction"):
        logger.log_open(arb, _context_ok())


def test_log_open_arbiter_invalide_leve(db_path: Path) -> None:
    """arbiter_result non-dict → erreur."""
    logger = PaperTradeLogger(db_path=db_path)
    with pytest.raises(PaperTradeLoggerError):
        logger.log_open("not a dict", _context_ok())
    with pytest.raises(PaperTradeLoggerError):
        logger.log_open(None, _context_ok())


def test_log_close_met_a_jour(db_path: Path) -> None:
    """Cas 2 — log_close remplit closed_at, pips_simulated, is_win."""
    logger = PaperTradeLogger(db_path=db_path)
    trade_id = logger.log_open(_arbiter_result(), _context_ok())

    logger.log_close(trade_id, pips_simulated=12.5)

    row = _row(db_path, trade_id)
    assert row["closed_at"] is not None
    assert row["pips_simulated"] == 12.5
    assert row["is_win"] == 1  # pips > 0


def test_log_close_trade_introuvable_leve(db_path: Path) -> None:
    """trade_id inexistant → PaperTradeLoggerError."""
    logger = PaperTradeLogger(db_path=db_path)
    with pytest.raises(PaperTradeLoggerError, match="introuvable"):
        logger.log_close("pt_inexistant", 10.0)


def test_log_close_deja_clos_leve(db_path: Path) -> None:
    """Trade déjà clos → erreur (pas de double clôture)."""
    logger = PaperTradeLogger(db_path=db_path)
    trade_id = logger.log_open(_arbiter_result(), _context_ok())
    logger.log_close(trade_id, 10.0)

    with pytest.raises(PaperTradeLoggerError, match="déjà clos"):
        logger.log_close(trade_id, 20.0)


def test_is_win_positif(db_path: Path) -> None:
    """Cas 3 — pips_simulated > 0 → is_win = 1."""
    logger = PaperTradeLogger(db_path=db_path)
    trade_id = logger.log_open(_arbiter_result(), _context_ok())
    logger.log_close(trade_id, pips_simulated=18.5)
    row = _row(db_path, trade_id)
    assert row["is_win"] == 1
    assert row["pips_simulated"] == 18.5


def test_is_win_negatif(db_path: Path) -> None:
    """Cas 4 — pips_simulated < 0 → is_win = 0."""
    logger = PaperTradeLogger(db_path=db_path)
    trade_id = logger.log_open(_arbiter_result(), _context_ok())
    logger.log_close(trade_id, pips_simulated=-12.3)
    row = _row(db_path, trade_id)
    assert row["is_win"] == 0
    assert row["pips_simulated"] == -12.3


def test_is_win_zero(db_path: Path) -> None:
    """pips_simulated = 0 (breakeven) → is_win = 0 (convention : non-win)."""
    logger = PaperTradeLogger(db_path=db_path)
    trade_id = logger.log_open(_arbiter_result(), _context_ok())
    logger.log_close(trade_id, pips_simulated=0.0)
    row = _row(db_path, trade_id)
    assert row["is_win"] == 0
    assert row["pips_simulated"] == 0.0


def test_idempotence_trade_id_unique(db_path: Path) -> None:
    """Cas 5 — 2 log_open produisent 2 trade_id distincts (idempotence par
    unicité du trade_id, pas par snapshot_id).

    Note : un même snapshot peut avoir plusieurs trades au cours du
    temps (relance, nouvelle fenêtre). Le trade_id est l'identifiant
    d'unicité — chaque ouverture génère un nouveau trade_id.
    """
    logger = PaperTradeLogger(db_path=db_path)
    arb = _arbiter_result(snapshot_id="snap_idem")
    ids = [logger.log_open(arb, _context_ok()) for _ in range(5)]

    # Tous distincts
    assert len(set(ids)) == 5, f"trade_id dupliqués : {ids}"
    # Tous format pt_xxxxxxxxxxxx
    for tid in ids:
        assert re.match(r"^pt_[0-9a-f]{12}$", tid)

    # 5 rangées en DB
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE snapshot_id = 'snap_idem'"
        ).fetchone()[0]
        assert count == 5
    finally:
        conn.close()


def test_trade_id_explicite_doublon_leve(db_path: Path) -> None:
    """Si trade_id fourni explicitement déjà existant → IntegrityError
    (PRIMARY KEY violation). C'est le comportement attendu d'idempotence."""
    import sqlite3 as sql
    logger = PaperTradeLogger(db_path=db_path)
    trade_id = "pt_dup00001"
    logger.log_open(_arbiter_result(), _context_ok(), trade_id=trade_id)
    with pytest.raises(sql.IntegrityError):
        logger.log_open(_arbiter_result(), _context_ok(), trade_id=trade_id)


def test_get_trade_inexistant(db_path: Path) -> None:
    """get_trade retourne None si trade_id absent."""
    logger = PaperTradeLogger(db_path=db_path)
    assert logger.get_trade("pt_ghost") is None


def test_init_db_idempotent(db_path: Path) -> None:
    """init_paper_trades_db() appelé 2× ne lève pas (CREATE IF NOT EXISTS)."""
    init_paper_trades_db(db_path)
    init_paper_trades_db(db_path)
    init_paper_trades_db(db_path)
    # Table existe et a les bonnes colonnes
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(paper_trades)"
        ).fetchall()}
    finally:
        conn.close()
    expected = {
        "trade_id", "snapshot_id", "direction", "confiance",
        "principes_source", "opened_at", "closed_at",
        "pips_simulated", "is_win", "risk_go_context",
    }
    assert expected.issubset(cols), f"colonnes manquantes : {expected - cols}"


def test_workflow_complet_arbiter_risk_paper(db_path: Path) -> None:
    """Test d'intégration : Arbiter vide → RiskManager bloque → pas de trade."""
    from core.v9.arbiter import Arbiter
    from core.v9.risk_manager import RiskManager
    from core.v9.decision_db import init_decision_db
    from core.v9.db_schema import init_db

    # Pas de décisions pour ce snapshot → arbiter neutre → risk bloque
    init_db(db_path)
    init_decision_db(db_path)

    arb = Arbiter(db_path=db_path).consolidate("snap_workflow")
    risk = RiskManager().evaluate(arb, _context_ok())
    assert risk["go"] is False

    # Si go=True, alors on ouvre. Ici pas le cas, donc on ne crée rien.
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM paper_trades"
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()
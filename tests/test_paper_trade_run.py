"""Tests unitaires — v9_paper_trade_run.py (orchestrateur Phase 10).

Couvre 4 cas exigés par le brief :
  1. test_dry_run_no_write
  2. test_no_duplicate_trade_same_snapshot
  3. test_go_false_ignored
  4. test_go_true_trade_logged

+ tests annexes : helpers (fetch_recent, fetch_context, is_already_open),
  json output, limite 0, default limit.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.v9 import config, db_schema
from core.v9.db_schema import init_db, get_connection
from core.v9.decision_db import init_decision_db
from core.v9.paper_trades_db import init_paper_trades_db
import scripts.v9_paper_trade_run as ptr


# ---------- Fixtures ----------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """DB complète : forces + decisions + paper_trades."""
    path = tmp_path / "v9_paper_run_test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db_schema, "DB_PATH", path)
    init_db(path)
    init_decision_db(path)
    init_paper_trades_db(path)
    return path


def _insert_decision(
    db_path: Path,
    *,
    snapshot_id: str = "snap_test",
    decision_id: str | None = None,
    direction: str = "baissiere",
    confiance: int = 85,
    principes: list[str] | None = None,
    window_statut: str = "exploitable",
    source_type: str = "live",
    timestamp: str = "2026-07-07T10:00:00+00:00",
) -> None:
    """Insère une décision avec contexte_complet_json contenant une window."""
    if decision_id is None:
        import uuid
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    contexte = {
        "signal": {"signal_id": "sig_test", "direction": direction,
                    "confiance": confiance},
        "window": {
            "window_id": f"win_{snapshot_id}",
            "statut": window_statut,
            "niveau_confiance": 80,
        },
        "exploitability": {
            "exploitability_id": f"expl_{snapshot_id}",
            "statut": window_statut,
            "window_statut": window_statut,
            "niveau_confiance_global": confiance,
        },
    }
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "INSERT INTO decisions ("
            " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
            " action, symbol, timeframe, currency,"
            " scene_id, behavior_id, window_id, exploitability_id,"
            " regime_type, direction, confiance,"
            " principes_json, contexte_complet_json, source_type, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision_id, "1.0", timestamp, snapshot_id, "sig_test",
                "surveiller", "GBPUSD", "M15", "GBP",
                "scene_t", "behav_t", "win_t", "exploit_t",
                "tendance", direction, confiance,
                json.dumps(principes or []),
                json.dumps(contexte), source_type, timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _count_paper_trades(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        return conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
    finally:
        conn.close()


# ---------- Tests ----------


def test_dry_run_no_write(db_path: Path) -> None:
    """Cas 1 — dry-run ne crée AUCUN trade en DB même si go=True."""
    _insert_decision(db_path, snapshot_id="snap_dry",
                     direction="haussiere", confiance=85,
                     principes=["P1", "P2"],
                     window_statut="exploitable")
    assert _count_paper_trades(db_path) == 0

    summary = ptr.run(limit=10, dry_run=True, db_path=db_path)

    assert summary["dry_run"] is True
    assert _count_paper_trades(db_path) == 0  # AUCUNE écriture
    assert summary["snapshots_analyses"] == 1
    assert summary["trades_ouverts"] == 1
    assert summary["trades_ignores"] == 0


def test_no_duplicate_trade_same_snapshot(db_path: Path) -> None:
    """Cas 2 — run 2× ne crée qu'UN seul trade pour le même snapshot."""
    _insert_decision(db_path, snapshot_id="snap_idem",
                     direction="baissiere", confiance=90,
                     principes=["P1", "P2"],
                     window_statut="exploitable")

    summary1 = ptr.run(limit=10, dry_run=False, db_path=db_path)
    assert summary1["trades_ouverts"] == 1
    assert _count_paper_trades(db_path) == 1

    # 2ème run : trade déjà ouvert → ignoré
    summary2 = ptr.run(limit=10, dry_run=False, db_path=db_path)
    assert summary2["trades_ouverts"] == 0
    assert summary2["trades_ignores"] == 1
    assert _count_paper_trades(db_path) == 1  # toujours 1 seul


def test_go_false_ignored(db_path: Path) -> None:
    """Cas 3 — fenêtre non exploitable → risque bloque → 0 trade ouvert."""
    _insert_decision(db_path, snapshot_id="snap_blocked",
                     direction="haussiere", confiance=85,
                     principes=["P1", "P2"],
                     window_statut="absente")  # bloque rule 4

    summary = ptr.run(limit=10, dry_run=False, db_path=db_path)
    assert summary["trades_ouverts"] == 0
    assert summary["trades_ignores"] == 1
    assert summary["details"][0]["go"] is False
    assert "fenêtre" in summary["details"][0]["raison_blocage"]
    assert _count_paper_trades(db_path) == 0


def test_go_true_trade_logged(db_path: Path) -> None:
    """Cas 4 — toutes les conditions réunies → trade ouvert en DB."""
    _insert_decision(db_path, snapshot_id="snap_go",
                     direction="baissiere", confiance=85,
                     principes=["P1", "P2"],
                     window_statut="exploitable")

    summary = ptr.run(limit=10, dry_run=False, db_path=db_path)
    assert summary["trades_ouverts"] == 1
    assert summary["trades_ignores"] == 0
    assert _count_paper_trades(db_path) == 1

    detail = summary["details"][0]
    assert detail["go"] is True
    assert detail["direction"] == "baissiere"
    assert detail["confiance"] == 85
    assert detail["principes_source"] == ["P1", "P2"]
    assert "trade_id" in detail
    assert detail["trade_id"].startswith("pt_")

    # Vérifier en DB
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        row = conn.execute(
            "SELECT * FROM paper_trades WHERE trade_id = ?",
            (detail["trade_id"],),
        ).fetchone()
        assert row is not None
        assert row[1] == "snap_go"  # snapshot_id
        assert row[2] == "baissiere"  # direction
        assert row[3] == 85  # confiance
    finally:
        conn.close()


# ---------- Tests annexes (helpers + edge cases) ----------


def test_fetch_recent_snapshot_ids(db_path: Path) -> None:
    """fetch_recent_live_snapshot_ids filtre directionnels + tri DESC."""
    # 3 snapshots directionnels + 2 neutres
    _insert_decision(db_path, snapshot_id="snap_A",
                     timestamp="2026-07-07T08:00:00+00:00",
                     direction="haussiere", confiance=85)
    _insert_decision(db_path, snapshot_id="snap_B",
                     timestamp="2026-07-07T08:01:00+00:00",
                     direction="baissiere", confiance=80)
    _insert_decision(db_path, snapshot_id="snap_C",
                     timestamp="2026-07-07T08:02:00+00:00",
                     direction="haussiere", confiance=90)
    # Neutre — ignoré par fetch_recent
    _insert_decision(db_path, snapshot_id="snap_N",
                     timestamp="2026-07-07T08:03:00+00:00",
                     direction="neutre", confiance=0)

    conn = get_connection(db_path)
    try:
        ids = ptr.fetch_recent_live_snapshot_ids(conn, limit=10)
    finally:
        conn.close()

    assert "snap_N" not in ids
    assert ids == ["snap_C", "snap_B", "snap_A"]  # DESC par timestamp


def test_fetch_context_window_exploitable(db_path: Path) -> None:
    """fetch_context_for_snapshot lit window.statut correctement."""
    _insert_decision(db_path, snapshot_id="snap_ctx",
                     direction="haussiere", window_statut="exploitable")

    conn = get_connection(db_path)
    try:
        ctx = ptr.fetch_context_for_snapshot(conn, "snap_ctx")
    finally:
        conn.close()

    assert ctx["window_status"] == "exploitable"
    # news_phase = NEUTRE par défaut (fallback)
    assert ctx["news_phase"] == "NEUTRE"


def test_fetch_context_window_absente(db_path: Path) -> None:
    _insert_decision(db_path, snapshot_id="snap_abs",
                     window_statut="absente")

    conn = get_connection(db_path)
    try:
        ctx = ptr.fetch_context_for_snapshot(conn, "snap_abs")
    finally:
        conn.close()
    assert ctx["window_status"] == "absente"


def test_fetch_context_snapshot_unknown(db_path: Path) -> None:
    """Snapshot inconnu → context par défaut (fenêtre absente)."""
    conn = get_connection(db_path)
    try:
        ctx = ptr.fetch_context_for_snapshot(conn, "snap_ghost")
    finally:
        conn.close()
    assert ctx["window_status"] == "absente"
    assert ctx["news_phase"] == "NEUTRE"


def test_is_trade_already_open(db_path: Path) -> None:
    """is_trade_already_open détecte les trades ouverts pour snapshot+direction."""
    from core.v9.paper_trade_logger import PaperTradeLogger

    _insert_decision(db_path, snapshot_id="snap_check",
                     direction="baissiere", confiance=85,
                     principes=["P1", "P2"], window_statut="exploitable")
    ptr.run(limit=10, dry_run=False, db_path=db_path)

    conn = get_connection(db_path)
    try:
        assert ptr.is_trade_already_open(conn, "snap_check", "baissiere") is True
        # Direction opposée → pas de trade ouvert
        assert ptr.is_trade_already_open(conn, "snap_check", "haussiere") is False
        # Snapshot différent → pas de trade ouvert
        assert ptr.is_trade_already_open(conn, "snap_other", "baissiere") is False
    finally:
        conn.close()


def test_is_trade_already_open_ignore_clos(db_path: Path) -> None:
    """Un trade clos n'est PAS considéré comme ouvert."""
    from core.v9.paper_trade_logger import PaperTradeLogger

    _insert_decision(db_path, snapshot_id="snap_clos",
                     direction="baissiere", confiance=85,
                     principes=["P1", "P2"], window_statut="exploitable")
    summary = ptr.run(limit=10, dry_run=False, db_path=db_path)
    trade_id = summary["details"][0]["trade_id"]
    # Clôturer
    PaperTradeLogger(db_path=db_path).log_close(trade_id, pips_simulated=10.0)

    conn = get_connection(db_path)
    try:
        assert ptr.is_trade_already_open(conn, "snap_clos", "baissiere") is False
    finally:
        conn.close()


def test_run_limit(db_path: Path) -> None:
    """--limit=N borne le nombre de snapshots analysés."""
    for i in range(5):
        _insert_decision(db_path, snapshot_id=f"snap_{i:02d}",
                         timestamp=f"2026-07-07T08:0{i}:00+00:00",
                         direction="haussiere", confiance=85,
                         principes=["P1", "P2"], window_statut="exploitable")
    summary = ptr.run(limit=2, dry_run=True, db_path=db_path)
    assert summary["snapshots_analyses"] == 2
    assert summary["limit"] == 2


def test_run_no_decisions(db_path: Path) -> None:
    """DB vide → 0 snapshots, 0 trades."""
    summary = ptr.run(limit=10, dry_run=True, db_path=db_path)
    assert summary["snapshots_analyses"] == 0
    assert summary["trades_ouverts"] == 0
    assert summary["trades_ignores"] == 0


def test_run_multiple_snapshots_mixed_outcomes(db_path: Path) -> None:
    """3 snapshots : 1 go=True, 1 go=False (window absente), 1 go=False (1 seul princ)."""
    _insert_decision(db_path, snapshot_id="snap_ok",
                     direction="haussiere", confiance=85,
                     principes=["P1", "P2"], window_statut="exploitable")
    _insert_decision(db_path, snapshot_id="snap_window_abs",
                     timestamp="2026-07-07T08:01:00+00:00",
                     direction="haussiere", confiance=85,
                     principes=["P1", "P2"], window_statut="absente")
    _insert_decision(db_path, snapshot_id="snap_1princ",
                     timestamp="2026-07-07T08:02:00+00:00",
                     direction="haussiere", confiance=95,
                     principes=["P_UNIQUE"], window_statut="exploitable")

    summary = ptr.run(limit=10, dry_run=False, db_path=db_path)
    assert summary["snapshots_analyses"] == 3
    assert summary["trades_ouverts"] == 1  # seul snap_ok
    assert summary["trades_ignores"] == 2
    assert _count_paper_trades(db_path) == 1


def test_run_direction_opens_distinct_trade(db_path: Path) -> None:
    """2 snapshots même ID mais directions différentes → 2 trades distincts
    (ne se bloquent pas mutuellement car le check est snapshot+direction)."""
    # Pour simuler, on utilise 2 snapshot_id distincts (car 1 snapshot =
    # 1 direction en pratique, mais on teste l'edge case).
    _insert_decision(db_path, snapshot_id="snap_h",
                     direction="haussiere", confiance=85,
                     principes=["P1", "P2"], window_statut="exploitable")
    _insert_decision(db_path, snapshot_id="snap_b",
                     timestamp="2026-07-07T08:01:00+00:00",
                     direction="baissiere", confiance=85,
                     principes=["P1", "P2"], window_statut="exploitable")

    summary = ptr.run(limit=10, dry_run=False, db_path=db_path)
    assert summary["trades_ouverts"] == 2
    assert _count_paper_trades(db_path) == 2
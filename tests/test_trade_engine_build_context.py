"""Tests unitaires — TradeEngine._build_context (fix 2026-07-15).

Régression : les requêtes précédentes filtraient `exploitability` et
`regime_snapshots` sur une colonne `snapshot_id` inexistante (clés réelles
`window_id`/`forces_snapshot_ref`) et `regime_snapshots.news_phase`
(colonne qui n'a jamais existé) -> `sqlite3.OperationalError` avalée
silencieusement par le `except Exception: pass`, `news_phase` et
`window_status` jamais peuplés (gate NEWS_SHOCK de risk_manager fail-open
en continu). `_build_context` lit maintenant `decisions` (déjà écrite par
`decision_logger.log()` avant l'appel de ce hook) + `NewsContext`.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from core.v9.db_schema import get_connection, init_all_dbs
from core.v9.decision_db import DECISIONS_COLUMNS
from core.v9.exploitability_db import EXPLOITABILITY_COLUMNS
from core.v9.trade_engine import TradeEngine


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_all_dbs(path)
    return path


def _insert_row(db_path: Path, table: str, columns: list[str], values: dict) -> None:
    conn = get_connection(db_path)
    try:
        col_names = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        conn.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            [values.get(c) for c in columns],
        )
        conn.commit()
    finally:
        conn.close()


def _insert_decision(
    db_path: Path,
    *,
    snapshot_id: str,
    exploitability_id: str | None,
    regime_type: str | None,
    timestamp: str,
) -> None:
    row = {c: None for c in DECISIONS_COLUMNS}
    row.update({
        "decision_id": f"dec-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
        "timestamp": timestamp, "snapshot_id": snapshot_id, "action": "preparer_entree",
        "symbol": "GBPUSD", "timeframe": "M15", "currency": "GBP",
        "exploitability_id": exploitability_id, "regime_type": regime_type,
        "direction": "haussiere", "confiance": 80, "source_type": "live",
        "created_at": timestamp, "low_confidence_block": 0,
    })
    _insert_row(db_path, "decisions", DECISIONS_COLUMNS, row)


def _insert_exploitability(db_path: Path, *, exploitability_id: str, statut: str) -> None:
    row = {c: None for c in EXPLOITABILITY_COLUMNS}
    row.update({
        "exploitability_id": exploitability_id, "schema_version": "1.0",
        "timestamp": "2026-07-15T14:00:00.000Z", "statut": statut, "stale": False,
    })
    _insert_row(db_path, "exploitability", EXPLOITABILITY_COLUMNS, row)


def test_build_context_reads_regime_and_window_status_from_decision(db_path: Path) -> None:
    snapshot_id = "snap-1"
    _insert_exploitability(db_path, exploitability_id="expl-1", statut="exploitable")
    _insert_decision(
        db_path, snapshot_id=snapshot_id, exploitability_id="expl-1",
        regime_type="CASSURE", timestamp="2026-07-15T14:00:00.000Z",
    )

    context = TradeEngine(db_path=db_path)._build_context(snapshot_id, "london")

    assert context["regime_type"] == "CASSURE"
    assert context["window_status"] == "exploitable"
    assert context["news_phase"] == "NEUTRE"


def test_build_context_maps_watchlist_to_exploitable(db_path: Path) -> None:
    snapshot_id = "snap-2"
    _insert_exploitability(db_path, exploitability_id="expl-2", statut="watchlist")
    _insert_decision(
        db_path, snapshot_id=snapshot_id, exploitability_id="expl-2",
        regime_type="EXTENSION", timestamp="2026-07-15T14:00:00.000Z",
    )

    context = TradeEngine(db_path=db_path)._build_context(snapshot_id, "london")

    assert context["window_status"] == "exploitable"


def test_build_context_degrades_gracefully_without_decision(db_path: Path) -> None:
    """Aucune décision pour ce snapshot (cas théorique — le hook n'est
    appelé qu'après decision_logger.log()) : ne lève jamais, reste
    fail-closed (pas de window_status = bloqué côté risk_manager)."""
    context = TradeEngine(db_path=db_path)._build_context("does-not-exist", "london")

    assert context["news_phase"] == "NEUTRE"
    assert "window_status" not in context

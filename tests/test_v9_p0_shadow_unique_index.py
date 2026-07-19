"""Tests RED/P0 fix : coexistence live/shadow dans les tables dérivées.

Bug initial (2026-07-19 22:00 UTC) : l'index UNIQUE sur signals.snapshot_id
et principle_evaluations(snapshot_id, principle_id, currency) ne différenciait
pas source_type, donc le INSERT OR REPLACE du shadow écrasait silencieusement
la ligne live.

Fix : nouvel index UNIQUE incluant source_type, avec dédup douce et
rollback transactionnel (voir core/v9/db_schema.py).

Robustesse de la migration (doublons intra-source_type, savepoint
rollback, idempotence) testée dans test_v9_p0_migration_robustness.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9 import orchestrator
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.principle_db import (
    PRINCIPLE_EVALUATIONS_COLUMNS,
    init_principle_db,
)
from core.v9.decision_db import init_decision_db
from core.v9.shadow_evaluator import run_shadow_pass
from core.v9.signal_db import init_signal_db


@pytest.fixture
def fresh_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "v9_forces.db"
    init_db(db_path)
    init_principle_db(db_path)
    init_signal_db(db_path)
    init_decision_db(db_path)
    return db_path


def _insert_forces_snapshot(db_path: Path, bar_time: int) -> str:
    sid = f"v9-p0-unique-{bar_time:04d}"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": sid,
        "schema_version": "1.0",
        "timestamp": f"2026-07-19T22:0{bar_time}:00.000Z",
        "source": "MT4_SDI",
        "symbol": "GBPUSD",
        "timeframe": "M5",
        "bar_time": bar_time,
        "is_closed_bar": True,
        "high": 1.29,
        "low": 1.28,
        "close": 1.285,
        "force_usd": 50,
        "force_gbp": 70,
        "force_eur": 45,
        "force_jpy": 50,
        "force_cad": 50,
        "force_chf": 50,
        "force_aud": 50,
        "force_nzd": 50,
        "direction": "haussiere",
        "vitesse": 2.5,
        "compression_extension_etat": "neutre",
        "compression_extension_intensite": 0,
        "stale": False,
        "age_ms": 100,
        "stale_threshold_ms": 35000,
        "created_at": f"2026-07-19T22:0{bar_time}:00.100Z",
    })
    conn = get_connection(db_path)
    try:
        placeholders = ", ".join("?" for _ in FORCES_COLUMNS)
        conn.execute(
            f"INSERT INTO forces_snapshots ({', '.join(FORCES_COLUMNS)}) "
            f"VALUES ({placeholders})",
            [row[c] for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()
    return sid


def test_live_signal_not_overwritten_by_shadow(
    fresh_db: Path, monkeypatch,
) -> None:
    """Chaîne live + passage shadow sur le même snapshot : les 2
    signaux (live + shadow) doivent coexister dans signals."""
    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "1")
    db_path = fresh_db
    memory_dir = db_path.parent / "memory"
    snapshot_id = _insert_forces_snapshot(db_path, bar_time=1)

    result = orchestrator.run_chain(snapshot_id, db_path=db_path,
                                    memory_dir=memory_dir)
    assert result["error"] is None
    assert result["signal_id"] is not None

    shadow = run_shadow_pass(snapshot_id, db_path=db_path)
    assert shadow is not None

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT source_type FROM signals WHERE snapshot_id = ? "
            "ORDER BY id",
            (snapshot_id,),
        ).fetchall()
    finally:
        conn.close()

    source_types = [r[0] for r in rows]
    assert "live" in source_types, (
        f"Signal live écrasée par shadow : {rows}"
    )
    assert "shadow" in source_types, (
        f"Shadow signal manquante après run_shadow_pass : {rows}"
    )


def test_live_principle_evaluation_not_overwritten_by_shadow(
    fresh_db: Path,
) -> None:
    """Insertion directe de 2 lignes (1 live + 1 shadow) sur le même
    (snapshot_id, principle_id, currency). Avec l'ancien index UNIQUE
    sans source_type, la 2e INSERT lève sqlite3.IntegrityError. Avec
    le nouvel index UNIQUE incluant source_type, les 2 lignes
    coexistent."""
    conn = get_connection(fresh_db)
    try:
        cols = ", ".join(PRINCIPLE_EVALUATIONS_COLUMNS)
        ph = ", ".join("?" for _ in PRINCIPLE_EVALUATIONS_COLUMNS)
        base_row = (
            "eval-test-001", "1.0", "2026-07-19T22:00:00.000Z",
            "v9-shadow-test-001",
            "PRICE_LAG_AT_NODE_BIRTH", "ACTIVE", "node_rule",
            "GBPUSD", "M5", "USD",
            1, "haussiere", 90, False, "conditions_remplies",
            "{}", "live", "2026-07-19T22:00:00.100Z",
        )
        conn.execute(
            f"INSERT INTO principle_evaluations ({cols}) VALUES ({ph})",
            base_row,
        )
        shadow_row = list(base_row)
        idx_src = PRINCIPLE_EVALUATIONS_COLUMNS.index("source_type")
        shadow_row[idx_src] = "shadow"
        shadow_row[0] = "eval-test-002"
        conn.execute(
            f"INSERT INTO principle_evaluations ({cols}) VALUES ({ph})",
            shadow_row,
        )
        conn.commit()

        rows = conn.execute(
            "SELECT source_type FROM principle_evaluations "
            "WHERE snapshot_id = 'v9-shadow-test-001' ORDER BY id"
        ).fetchall()
        source_types = [r[0] for r in rows]
        assert source_types == ["live", "shadow"], (
            f"Coexistence live+shadow attendue, trouvé {source_types}"
        )
    finally:
        conn.close()


def test_signals_unique_index_includes_source_type(fresh_db: Path) -> None:
    """L'index UNIQUE signals doit inclure source_type pour permettre
    la coexistence live+shadow sur le même snapshot_id."""
    conn = get_connection(fresh_db)
    try:
        idx = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='index' AND name='idx_signals_snapshot_source_type'"
        ).fetchone()
    finally:
        conn.close()
    assert idx is not None, "idx_signals_snapshot_source_type manquant"
    sql = idx[0]
    assert "source_type" in sql, (
        f"idx_signals_snapshot_source_type doit inclure source_type : {sql}"
    )


def test_principle_evaluations_unique_index_includes_source_type(
    fresh_db: Path,
) -> None:
    """L'index UNIQUE principle_evaluations doit inclure source_type
    pour permettre la coexistence live+shadow."""
    conn = get_connection(fresh_db)
    try:
        idx = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='index' "
            "AND name='idx_pe_snapshot_principle_currency_source'"
        ).fetchone()
    finally:
        conn.close()
    assert idx is not None
    sql = idx[0]
    assert "source_type" in sql, (
        f"idx_pe_snapshot_principle_currency_source doit inclure source_type : {sql}"
    )


def test_live_decision_not_overwritten_by_shadow(
    fresh_db: Path, monkeypatch,
) -> None:
    """Le shadow ne doit JAMAIS écraser la decision live du même
    snapshot (la table decisions utilise déjà decision_id namespacé
    via ShadowDecisionLogger — fix antérieur préservé)."""
    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "1")
    db_path = fresh_db
    memory_dir = db_path.parent / "memory"
    snapshot_id = _insert_forces_snapshot(db_path, bar_time=3)

    orchestrator.run_chain(snapshot_id, db_path=db_path,
                            memory_dir=memory_dir)
    run_shadow_pass(snapshot_id, db_path=db_path)

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT source_type, decision_id FROM decisions "
            "WHERE snapshot_id = ? ORDER BY id",
            (snapshot_id,),
        ).fetchall()
    finally:
        conn.close()

    source_types = [r[0] for r in rows]
    assert "live" in source_types, (
        f"Decision live écrasée par shadow : {rows}"
    )
    assert "shadow" in source_types, (
        f"Decision shadow manquante : {rows}"
    )
    assert len(rows) == 2, f"Coexistence attendue, trouvé {rows}"

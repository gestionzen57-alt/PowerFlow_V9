"""P0 2026-07-19 — coexistence live/shadow dans les tables dérivées.

Bug observé (P0 a) : `signals` et `principle_evaluations` ont un index
UNIQUE sur `snapshot_id` SANS `source_type`. Le shadow rejoue un snapshot
déjà traité en live et fait `INSERT OR REPLACE`, ce qui **écrase la
ligne live** au lieu de coexister.

Reproduction : insérer une ligne live dans `signals`, puis
`INSERT OR REPLACE` une ligne shadow avec le même `snapshot_id`.
Sans fix : la ligne live est perdue (1 ligne, source_type=shadow).
Avec fix : les deux lignes coexistent (2 lignes, source_type ∈ {live, shadow}).

DOCTRINE : R7 régression autorisée par motion CEO (« go corriger P0 »),
R18 code pur, R25' kill switch OFF par défaut, R26 tests obligatoires.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.decision_db import init_decision_db
from core.v9.principle_db import init_principle_db
from core.v9.signal_db import init_signal_db
from core.v9.shadow_evaluator import SOURCE_TYPE_SHADOW, run_shadow_pass
from core.v9 import orchestrator


def _insert_forces_snapshot(db_path: Path, *, symbol: str = "GBPUSD",
                            bar_time: int = 0) -> str:
    snapshot_id = f"v9-p0-unique-{bar_time:04d}"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id,
        "schema_version": "1.0",
        "timestamp": f"2026-07-19T21:{bar_time:02d}:00.000Z",
        "source": "MT4_SDI",
        "symbol": symbol,
        "timeframe": "M5",
        "bar_time": bar_time,
        "is_closed_bar": True,
        "high": 1.2900, "low": 1.2800, "close": 1.2860,
        "force_usd": 50.0, "force_gbp": 70.0, "force_eur": 45.0,
        "force_jpy": 50.0, "force_cad": 50.0, "force_chf": 50.0,
        "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "vitesse": 2.5,
        "compression_extension_etat": "neutre",
        "compression_extension_intensite": 0.0,
        "stale": False, "age_ms": 100, "stale_threshold_ms": 35000,
        "created_at": f"2026-07-19T21:{bar_time:02d}:00.100Z",
    })
    conn = get_connection(db_path)
    try:
        cols = ", ".join(FORCES_COLUMNS)
        ph = ", ".join("?" for _ in FORCES_COLUMNS)
        conn.execute(
            f"INSERT INTO forces_snapshots ({cols}) VALUES ({ph})",
            [row.get(c) for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()
    return snapshot_id


@pytest.fixture
def fresh_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "v9_forces.db"
    init_db(db_path)
    init_principle_db(db_path)
    init_signal_db(db_path)
    init_decision_db(db_path)
    return db_path


def test_live_signal_not_overwritten_by_shadow(fresh_db: Path,
                                               monkeypatch) -> None:
    """Le shadow ne doit JAMAIS écraser la ligne live du même snapshot."""
    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "1")
    db_path = fresh_db
    memory_dir = db_path.parent / "memory"
    snapshot_id = _insert_forces_snapshot(db_path, bar_time=1)

    # Chaîne live d'abord.
    result = orchestrator.run_chain(snapshot_id, db_path=db_path,
                                    memory_dir=memory_dir)
    assert result["error"] is None
    assert result["signal_id"] is not None

    # Puis passage shadow sur le même snapshot.
    shadow = run_shadow_pass(snapshot_id, db_path=db_path)
    assert shadow is not None

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT source_type, signal_id FROM signals "
            "WHERE snapshot_id = ? ORDER BY id",
            (snapshot_id,),
        ).fetchall()
    finally:
        conn.close()

    source_types = [r[0] for r in rows]
    assert "live" in source_types, (
        f"Live signal écrasée par shadow : {rows}"
    )
    assert "shadow" in source_types, (
        f"Shadow signal manquante après run_shadow_pass : {rows}"
    )
    assert len(rows) == 2, (
        f"Coexistence live+shadow attendue, trouvé {rows}"
    )


def test_live_principle_evaluation_not_overwritten_by_shadow(
    fresh_db: Path, monkeypatch,
) -> None:
    """Le shadow doit écrire ses propres principle_evaluations sans
    toucher celles de la chaîne live (8 devises/snapshot)."""
    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "1")
    db_path = fresh_db
    memory_dir = db_path.parent / "memory"
    snapshot_id = _insert_forces_snapshot(db_path, bar_time=2)

    orchestrator.run_chain(snapshot_id, db_path=db_path,
                            memory_dir=memory_dir)
    run_shadow_pass(snapshot_id, db_path=db_path)

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT source_type, COUNT(*) FROM principle_evaluations "
            "WHERE snapshot_id = ? GROUP BY source_type",
            (snapshot_id,),
        ).fetchall()
    finally:
        conn.close()

    counts = {r[0]: r[1] for r in rows}
    assert counts.get("live", 0) > 0, (
        f"Principes live absents : {counts}"
    )
    assert counts.get("shadow", 0) > 0, (
        f"Principes shadow absents : {counts}"
    )

def test_live_principle_evaluation_not_overwritten_by_shadow(
    fresh_db: Path, monkeypatch,
) -> None:
    """Le shadow doit écrire ses propres principle_evaluations sans
    toucher celles de la chaîne live (index UNIQUE incluant source_type).

    Test ciblé : on insère directement 2 lignes (1 live + 1 shadow) sur
    le même (snapshot_id, principle_id, currency). Avec l'ancien index
    UNIQUE(snapshot_id, principle_id, currency), la 2e INSERT lève
    sqlite3.IntegrityError. Avec le nouvel index UNIQUE incluant
    source_type, les 2 lignes coexistent.
    """
    from core.v9.db_schema import get_connection as _gconn
    from core.v9.principle_db import PRINCIPLE_EVALUATIONS_COLUMNS

    conn = get_connection(fresh_db)
    try:
        # Pré-requis : lignes scenes+behaviors+windows+exploitability
        # pour que principle_evaluations soit insérable.
        # Ici on insère directement en bypassing la chaîne (test ciblé
        # sur l'index, pas sur le pipeline complet).
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
        # INSERT shadow sur le même (snapshot, principle, currency)
        # avec source_type='shadow'. Avec l'ancien index UNIQUE, ça lève
        # IntegrityError (UNIQUE constraint failed). Avec le nouvel
        # index UNIQUE incluant source_type, ça passe.
        shadow_row = list(base_row)
        shadow_row[4] = "PRICE_LAG_AT_NODE_BIRTH"  # principle_id
        shadow_row[10] = 1  # triggered
        shadow_row[15] = "shadow"  # source_type
        # Trouver l'index de source_type dans PRINCIPLE_EVALUATIONS_COLUMNS
        idx_src = PRINCIPLE_EVALUATIONS_COLUMNS.index("source_type")
        # Recalculer shadow_row avec source_type=shadow
        shadow_row = list(base_row)
        shadow_row[idx_src] = "shadow"
        shadow_row[0] = "eval-test-002"  # evaluation_id différent
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

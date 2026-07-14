"""Tests — hook shadow mode (P2) dans orchestrator.run_chain().

Vérifie que le hook shadow est bien OFF par défaut (R25'), qu'il produit
une décision shadow distincte quand activé, et qu'il ne bloque jamais
run_chain() même s'il échoue (règle 6 — jamais de crash orchestrateur).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.v9 import orchestrator
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]


def _insert_forces_snapshot(db_path: Path, *, bar_time: int = 0) -> str:
    snapshot_id = f"v9-orchshadow-{bar_time:04d}"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id,
        "schema_version": "1.0",
        "timestamp": f"2026-07-13T11:{bar_time:02d}:00.000Z",
        "source": "MT4_SDI",
        "symbol": "GBPUSD",
        "timeframe": "M5",
        "bar_time": bar_time,
        "is_closed_bar": True,
        "high": 1.2900, "low": 1.2800, "close": 1.2860,
        "force_usd": 50.0, "force_gbp": 40.0, "force_eur": 65.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "vitesse": 2.5,
        "compression_extension_etat": "neutre", "compression_extension_intensite": 0.0,
        "stale": False, "age_ms": 100, "stale_threshold_ms": 35000,
        "created_at": f"2026-07-13T11:{bar_time:02d}:00.100Z",
    })
    conn = get_connection(db_path)
    try:
        col_names = ", ".join(FORCES_COLUMNS)
        placeholders = ", ".join(["?"] * len(FORCES_COLUMNS))
        conn.execute(
            f"INSERT INTO forces_snapshots ({col_names}) VALUES ({placeholders})",
            [row.get(c) for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()
    return snapshot_id


def _decision_source_types(db_path: Path, snapshot_id: str) -> set[str]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT source_type FROM decisions WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def test_shadow_hook_off_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("V9_SHADOW_MODE_ENABLED", raising=False)
    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "0")  # override fichier réel
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    init_db(db_path)
    snapshot_id = _insert_forces_snapshot(db_path)

    result = orchestrator.run_chain(snapshot_id, db_path=db_path, memory_dir=memory_dir)

    assert result["error"] is None
    assert _decision_source_types(db_path, snapshot_id) == {"live"}


def test_shadow_hook_enabled_produces_shadow_decision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "1")
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    init_db(db_path)
    snapshot_id = _insert_forces_snapshot(db_path)

    result = orchestrator.run_chain(snapshot_id, db_path=db_path, memory_dir=memory_dir)

    assert result["error"] is None
    assert _decision_source_types(db_path, snapshot_id) == {"live", "shadow"}


def test_shadow_hook_failure_never_blocks_run_chain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "1")
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    init_db(db_path)
    snapshot_id = _insert_forces_snapshot(db_path)

    from core.v9 import shadow_evaluator

    def _boom(*args, **kwargs):
        raise RuntimeError("shadow DB indisponible")

    monkeypatch.setattr(shadow_evaluator, "run_shadow_pass", _boom)

    result = orchestrator.run_chain(snapshot_id, db_path=db_path, memory_dir=memory_dir)

    assert result["error"] is None
    assert result["decision_id"] is not None
    assert _decision_source_types(db_path, snapshot_id) == {"live"}

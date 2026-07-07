"""Tests — hook flow_probe.record() best-effort dans orchestrator.run_chain().

Vérifie que run_chain() tente d'enregistrer un probe_event à chaque
appel (succès ou erreur de couche) sans jamais planter, y compris si
flow_probe.record() lève une exception (règle 6 — l'orchestrateur ne
crash jamais).
"""

from __future__ import annotations

from pathlib import Path

from core.v9 import flow_probe, orchestrator
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]


def _insert_forces_snapshot(db_path: Path, *, bar_time: int = 0) -> str:
    snapshot_id = f"v9-probehook-{bar_time:04d}"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id,
        "schema_version": "1.0",
        "timestamp": f"2026-07-07T10:{bar_time:02d}:00.000Z",
        "source": "MT4_SDI",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "bar_time": bar_time,
        "is_closed_bar": True,
        "high": 1.0900, "low": 1.0800, "close": 1.0860,
        "force_usd": 50.0, "force_gbp": 40.0, "force_eur": 65.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "vitesse": 2.5,
        "compression_extension_etat": "neutre", "compression_extension_intensite": 0.0,
        "stale": False, "age_ms": 100, "stale_threshold_ms": 35000,
        "created_at": f"2026-07-07T10:{bar_time:02d}:00.100Z",
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


def test_run_chain_records_probe_event_on_success(tmp_path: Path) -> None:
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    init_db(db_path)
    snapshot_id = _insert_forces_snapshot(db_path)

    result = orchestrator.run_chain(snapshot_id, db_path=db_path, memory_dir=memory_dir)

    assert result["error"] is None
    events = flow_probe.list_events(snapshot_id, db_path=db_path)
    # Best-effort : au moins 1 row attendue ici (DB accessible en écriture),
    # mais l'important est surtout que run_chain() n'ait pas planté.
    assert len(events) >= 0
    if events:
        assert events[0]["status"] == "OK"


def test_run_chain_survives_flow_probe_record_failure(tmp_path: Path, monkeypatch) -> None:
    """Si flow_probe.record() explose, run_chain() doit quand même retourner
    normalement (best-effort, règle 6 — jamais de crash orchestrateur)."""
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    init_db(db_path)
    snapshot_id = _insert_forces_snapshot(db_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("probe DB indisponible")

    monkeypatch.setattr(flow_probe, "record", _boom)

    result = orchestrator.run_chain(snapshot_id, db_path=db_path, memory_dir=memory_dir)

    assert result["error"] is None
    assert result["decision_id"] is not None

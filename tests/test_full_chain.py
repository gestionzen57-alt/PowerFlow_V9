"""Smoke test — chaîne cognitive complète PowerFlow V9.

Vérifie que Forces → Scènes → Comportements → Fenêtres → Exploitabilité
s'enchaîne sans casser, un snapshot de forces alimentant chaque couche
via la précédente jusqu'à une évaluation d'exploitabilité. N'évalue pas
la qualité des heuristiques (aucune assertion de calibration) — objectif
unique : la chaîne ne casse pas.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from core.v9.behavior_analyzer import BehaviorAnalyzer
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.exploitability_evaluator import STATUTS, ExploitabilityEvaluator
from core.v9.scene_builder import SceneBuilder
from core.v9.window_gate import WindowGate

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]


def _insert_forces_snapshot(db_path: Path) -> str:
    snapshot_id = f"v9-chain-{uuid.uuid4().hex[:8]}"
    row = {
        "snapshot_id": snapshot_id,
        "schema_version": "1.0",
        "timestamp": "2026-07-05T14:00:00.000Z",
        "source": "MT4_SDI",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "bar_time": None, "bar_close_time": None, "server_time": None, "capture_time": None,
        "shift": None, "is_closed_bar": True,
        "open": None, "high": 1.0900, "low": 1.0800, "close": 1.0860,
        "tick_volume": None, "spread_points": None, "spread_price": None,
        "bid": None, "ask": None, "mid": None,
        "force_usd": 50.0, "force_gbp": 40.0, "force_eur": 65.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "vitesse": 2.5,
        "croisement_detecte": False, "croisement_partenaire": None, "croisement_direction": None,
        "recroisement_detecte": False, "recroisement_contexte": None,
        "rejet_repulsion_detecte": False, "rejet_intensite": None,
        "compression_extension_etat": "neutre", "compression_extension_intensite": 0.0,
        "stale": False, "age_ms": 100, "stale_threshold_ms": 35000,
        "created_at": "2026-07-05T14:00:00.100Z",
    }
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


def test_full_chain_forces_to_exploitability(tmp_path: Path) -> None:
    db_path = tmp_path / "v9_chain_test.db"
    memory_dir = tmp_path / "memory"
    init_db(db_path)

    snapshot_id = _insert_forces_snapshot(db_path)

    scene_builder = SceneBuilder(db_path=db_path, config={"memory_dir": memory_dir})
    scene = scene_builder.build_scene(snapshot_id)
    scene_builder._write_scene_to_db(scene)
    assert scene["scene_id"]

    behavior_analyzer = BehaviorAnalyzer(db_path=db_path, config={"memory_dir": memory_dir})
    behavior = behavior_analyzer.analyze_scene(scene["scene_id"])
    assert behavior["behavior_id"]
    assert behavior["scene_id_ref"] == scene["scene_id"]

    window_gate = WindowGate(db_path=db_path, memory_path=memory_dir / "memory_temp.md")
    window = window_gate.evaluate_behavior(behavior["behavior_id"])
    assert window["window_id"]
    assert window["behavior_source"]["behavior_id"] == behavior["behavior_id"]

    evaluator = ExploitabilityEvaluator(db_path=db_path, config={"memory_dir": memory_dir})
    evaluation = evaluator.evaluate_window(window["window_id"])
    assert evaluation["window_source"]["window_id"] == window["window_id"]
    assert evaluation["statut"] in STATUTS

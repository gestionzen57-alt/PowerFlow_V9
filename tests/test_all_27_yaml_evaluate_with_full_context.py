"""Test unitaire — les principes du catalogue s'évaluent sans KeyError avec un
contexte complet (scène/comportement/fenêtre/exploitabilité/régime/zone présents),
Phase C2 doctrine realign. Catalogue = 25 (Phase 9.8 B5 : GRAMMAR_GRAVITE/INVERSION
archivés), promotion SHADOW→ACTIVE (C1) rejetée en Phase E — PRINCIPLE_ACTIVE_IDS
reste à 10, sans effet sur ce test (evaluate_principles couvre tout le catalogue,
ACTIVE et SHADOW)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.v9.behavior_db import BEHAVIOR_COLUMNS, init_behavior_db
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.exploitability_db import EXPLOITABILITY_COLUMNS, init_exploitability_db
from core.v9.principle_engine import PrincipleEngine
from core.v9.regime_db import REGIME_SNAPSHOTS_COLUMNS, init_regime_db
from core.v9.scene_db import SCENES_COLUMNS, init_scene_db
from core.v9.window_db import WINDOWS_COLUMNS, init_window_db
from core.v9.zone_db import ZONE_DIAGNOSTICS_COLUMNS, init_zone_db

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    return path


def _row(columns: list[str], **overrides) -> dict:
    row = {c: None for c in columns}
    row.update(overrides)
    return row


def _insert_full_chain(db_path: Path) -> str:
    init_behavior_db(db_path)
    init_scene_db(db_path)
    init_window_db(db_path)
    init_exploitability_db(db_path)
    init_regime_db(db_path)
    init_zone_db(db_path)

    conn = get_connection(db_path)
    try:
        snapshot_id = "fs_full_ctx_test_0001"
        forces = _row(
            FORCES_COLUMNS,
            snapshot_id=snapshot_id, schema_version="1.0",
            timestamp="2026-07-08T10:00:00.000Z", source="MT4_SDI",
            symbol="GBPUSD", timeframe="H1", mid=1.3400, stale=False,
            created_at="2026-07-08T10:00:00.100Z",
        )
        for d in DEVISES:
            forces[f"force_{d.lower()}"] = 50.0
        conn.execute(
            f"INSERT INTO forces_snapshots ({', '.join(FORCES_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(FORCES_COLUMNS))})",
            [forces[c] for c in FORCES_COLUMNS],
        )

        scene = _row(
            SCENES_COLUMNS,
            scene_id="scene_full_ctx_0001", schema_version="1.0",
            timestamp="2026-07-08T10:00:00.000Z", forces_snapshot_ref=snapshot_id,
            coalitions_json="[]", antagonismes_json="[]", cinematique_json="{}",
            risk_assessment_json="{}", confluences_mtf_json="{}",
            contexte_temporel_json="{}", created_at="2026-07-08T10:00:00.200Z",
        )
        conn.execute(
            f"INSERT INTO scenes ({', '.join(SCENES_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(SCENES_COLUMNS))})",
            [scene[c] for c in SCENES_COLUMNS],
        )

        behavior = _row(
            BEHAVIOR_COLUMNS,
            behavior_id="behavior_full_ctx_0001", schema_version="1.0",
            timestamp="2026-07-08T10:00:00.000Z", scene_id_ref="scene_full_ctx_0001",
            qualification="test", stale=False, created_at="2026-07-08T10:00:00.300Z",
        )
        conn.execute(
            f"INSERT INTO behaviors ({', '.join(BEHAVIOR_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(BEHAVIOR_COLUMNS))})",
            [behavior[c] for c in BEHAVIOR_COLUMNS],
        )

        window = _row(
            WINDOWS_COLUMNS,
            window_id="window_full_ctx_0001", schema_version="1.0",
            timestamp="2026-07-08T10:00:00.000Z", behavior_id="behavior_full_ctx_0001",
            statut="exploitable", conditions_invalidation_json="[]", stale=False,
            created_at="2026-07-08T10:00:00.400Z",
        )
        conn.execute(
            f"INSERT INTO windows ({', '.join(WINDOWS_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(WINDOWS_COLUMNS))})",
            [window[c] for c in WINDOWS_COLUMNS],
        )

        exploitability = _row(
            EXPLOITABILITY_COLUMNS,
            exploitability_id="expl_full_ctx_0001", schema_version="1.0",
            timestamp="2026-07-08T10:00:00.000Z", window_id="window_full_ctx_0001",
            statut="exploitable", niveau_confiance_global=80, stale=False,
            created_at="2026-07-08T10:00:00.500Z",
        )
        conn.execute(
            f"INSERT INTO exploitability ({', '.join(EXPLOITABILITY_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(EXPLOITABILITY_COLUMNS))})",
            [exploitability[c] for c in EXPLOITABILITY_COLUMNS],
        )

        for d in DEVISES:
            regime = _row(
                REGIME_SNAPSHOTS_COLUMNS,
                regime_id=f"regime_full_ctx_{d}", schema_version="1.0",
                timestamp="2026-07-08T10:00:00.000Z", forces_snapshot_ref=snapshot_id,
                currency=d, regime_type="trend", stale=False,
                created_at="2026-07-08T10:00:00.600Z",
            )
            conn.execute(
                f"INSERT INTO regime_snapshots ({', '.join(REGIME_SNAPSHOTS_COLUMNS)}) "
                f"VALUES ({', '.join(['?'] * len(REGIME_SNAPSHOTS_COLUMNS))})",
                [regime[c] for c in REGIME_SNAPSHOTS_COLUMNS],
            )
            zone = _row(
                ZONE_DIAGNOSTICS_COLUMNS,
                zone_id=f"zone_full_ctx_{d}", schema_version="1.0",
                timestamp="2026-07-08T10:00:00.000Z", forces_snapshot_ref=snapshot_id,
                currency=d, state="EARLY_EXTREME", prev_state="NEUTRAL",
                z_current=1.2, z_extreme_dir="up", prev_z_extreme_dir=None,
                bars_in_extreme=1, tension_score=5.0, absorbed_pullback_count=0,
                stale=False, created_at="2026-07-08T10:00:00.700Z",
            )
            conn.execute(
                f"INSERT INTO zone_diagnostics ({', '.join(ZONE_DIAGNOSTICS_COLUMNS)}) "
                f"VALUES ({', '.join(['?'] * len(ZONE_DIAGNOSTICS_COLUMNS))})",
                [zone[c] for c in ZONE_DIAGNOSTICS_COLUMNS],
            )
        conn.commit()
    finally:
        conn.close()
    return snapshot_id


def test_all_25_principles_evaluate_without_crash_full_context(db_path: Path):
    snapshot_id = _insert_full_chain(db_path)
    engine = PrincipleEngine(db_path=db_path)
    evaluations = engine.evaluate_principles(snapshot_id)
    assert len(evaluations) > 0
    evaluated_ids = {e["principle_id"] for e in evaluations}
    assert len(evaluated_ids) == 25


def test_all_evaluations_have_a_reason_never_none(db_path: Path):
    snapshot_id = _insert_full_chain(db_path)
    engine = PrincipleEngine(db_path=db_path)
    evaluations = engine.evaluate_principles(snapshot_id)
    for e in evaluations:
        assert e["reason"] is not None

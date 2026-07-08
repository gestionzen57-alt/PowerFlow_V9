"""Test unitaire — les 27 principes s'évaluent sans exception avec un contexte
minimal (aucune scène/comportement/fenêtre/exploitabilité/régime/zone),
Phase C2 doctrine realign (vérifie les fallbacks explicites ajoutés à
_build_currency_context)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.v9.behavior_db import init_behavior_db
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.exploitability_db import init_exploitability_db
from core.v9.principle_engine import PrincipleEngine
from core.v9.regime_db import init_regime_db
from core.v9.scene_db import init_scene_db
from core.v9.window_db import init_window_db
from core.v9.zone_db import init_zone_db

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    return path


def _insert_forces_only(db_path: Path, timeframe: str) -> str:
    # Tables aval créées mais vides — "minimal" signifie "aucune scène/
    # comportement/fenêtre/exploitabilité/régime/zone produite en amont",
    # pas "tables absentes" (ce dernier cas est un bug d'infra, hors
    # périmètre de ce test qui cible les fallbacks de _load_shared_context).
    init_behavior_db(db_path)
    init_scene_db(db_path)
    init_window_db(db_path)
    init_exploitability_db(db_path)
    init_regime_db(db_path)
    init_zone_db(db_path)

    conn = get_connection(db_path)
    try:
        snapshot_id = f"fs_minimal_ctx_{timeframe.lower()}"
        row = {c: None for c in FORCES_COLUMNS}
        row.update(
            snapshot_id=snapshot_id, schema_version="1.0",
            timestamp="2026-07-08T10:00:00.000Z", source="MT4_SDI",
            symbol="GBPUSD", timeframe=timeframe, mid=1.3400, stale=False,
            created_at="2026-07-08T10:00:00.100Z",
        )
        for d in DEVISES:
            row[f"force_{d.lower()}"] = 50.0
        conn.execute(
            f"INSERT INTO forces_snapshots ({', '.join(FORCES_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(FORCES_COLUMNS))})",
            [row[c] for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()
    return snapshot_id


def test_no_principle_crashes_on_minimal_context_h1(db_path: Path):
    snapshot_id = _insert_forces_only(db_path, "H1")
    engine = PrincipleEngine(db_path=db_path)
    evaluations = engine.evaluate_principles(snapshot_id)
    assert len(evaluations) > 0
    for e in evaluations:
        assert e["triggered"] in (True, False)


def test_no_principle_crashes_on_minimal_context_m5(db_path: Path):
    snapshot_id = _insert_forces_only(db_path, "M5")
    engine = PrincipleEngine(db_path=db_path)
    evaluations = engine.evaluate_principles(snapshot_id)
    assert len(evaluations) > 0
    for e in evaluations:
        assert e["reason"] is not None

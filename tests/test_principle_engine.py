"""Tests unitaires — PrincipleEngine (couche Décision, Phase 9) PowerFlow V9."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from core.v9.behavior_db import BEHAVIOR_COLUMNS, init_behavior_db
from core.v9.config import PRINCIPLE_ACTIVE_IDS, PRINCIPLES_DIR
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.exploitability_db import EXPLOITABILITY_COLUMNS, init_exploitability_db
from core.v9.principle_engine import (
    PrincipleEngine,
    PrincipleEngineError,
    PrincipleRecord,
    _compute_confidence,
    _normalize_direction,
    _resolve_direction,
    evaluate_condition,
    evaluate_principle,
    load_principles_from_yaml,
)
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


# ── Chargement du catalogue YAML ──────────────────────────
def test_loads_all_27_principles():
    principles = load_principles_from_yaml()
    assert len(principles) == 27
    assert len({p.principle_id for p in principles}) == 27


def test_kind_distribution_9_node_rule_18_grammar():
    principles = load_principles_from_yaml()
    node_rule = [p for p in principles if p.kind == "node_rule"]
    grammar = [p for p in principles if p.kind == "grammar"]
    assert len(node_rule) == 9
    assert len(grammar) == 18


def test_all_active_ids_exist_in_catalogue():
    principles = load_principles_from_yaml()
    ids = {p.principle_id for p in principles}
    for active_id in PRINCIPLE_ACTIVE_IDS:
        assert active_id in ids


def test_v9_status_split_10_active_17_shadow():
    principles = load_principles_from_yaml()
    active = [p for p in principles if p.v9_status == "ACTIVE"]
    shadow = [p for p in principles if p.v9_status == "SHADOW"]
    assert len(active) == 10
    assert len(shadow) == 17


def test_principles_dir_matches_config():
    principles = load_principles_from_yaml(PRINCIPLES_DIR)
    assert len(principles) == 27


# ── matches_scope ──────────────────────────────────────────
def test_matches_scope_all_timeframes_all_currencies():
    p = PrincipleRecord(
        principle_id="X", version=1, origin="", kind="grammar", source_status="active",
        scope_timeframes="ALL", scope_currencies="ALL",
    )
    assert p.matches_scope("EURUSD", "M30", "GBP")


def test_matches_scope_restricted_timeframe_excludes_others():
    p = PrincipleRecord(
        principle_id="X", version=1, origin="", kind="node_rule", source_status="active",
        scope_timeframes=[60], scope_currencies="ALL",
    )
    assert p.matches_scope("EURUSD", "H1", "GBP")
    assert not p.matches_scope("EURUSD", "M5", "GBP")


def test_matches_scope_restricted_currency_excludes_others():
    p = PrincipleRecord(
        principle_id="X", version=1, origin="", kind="node_rule", source_status="active",
        scope_timeframes="ALL", scope_currencies=["GBP", "USD"],
    )
    assert p.matches_scope("EURUSD", "M5", "GBP")
    assert not p.matches_scope("EURUSD", "M5", "JPY")


# ── evaluate_condition ─────────────────────────────────────
@pytest.mark.parametrize(
    "op,value,target,expected",
    [
        ("==", "RUPTURE", "RUPTURE", True),
        ("==", "RUPTURE", "PALIER", False),
        ("!=", "NONE", "NONE", False),
        ("!=", "UP", "NONE", True),
        (">=", 1.5, 1.0, True),
        (">=", 0.5, 1.0, False),
        ("<=", 2, 3, True),
        ("<=", 4, 3, False),
    ],
)
def test_evaluate_condition_simple_ops(op, value, target, expected):
    cond = {"field": "f", "op": op, "value": target}
    assert evaluate_condition(cond, {"f": value}) is expected


def test_evaluate_condition_in_and_not_in():
    cond_in = {"field": "state", "op": "in", "value": ["ACCUMULATING", "LEAKING"]}
    assert evaluate_condition(cond_in, {"state": "LEAKING"}) is True
    assert evaluate_condition(cond_in, {"state": "NEUTRAL"}) is False

    cond_not_in = {"field": "h1_state", "op": "not_in", "value": ["NEUTRAL", None]}
    assert evaluate_condition(cond_not_in, {"h1_state": "ACCUMULATING"}) is True
    assert evaluate_condition(cond_not_in, {"h1_state": "NEUTRAL"}) is False


def test_evaluate_condition_is_not_null():
    cond = {"field": "pf_mid", "op": "is_not_null"}
    assert evaluate_condition(cond, {"pf_mid": 1.085}) is True
    assert evaluate_condition(cond, {"pf_mid": None}) is False
    assert evaluate_condition(cond, {}) is False


def test_evaluate_condition_missing_field_is_always_false():
    for op, val in (("==", "X"), ("!=", "X"), (">=", 1), ("<=", 1), ("in", ["X"]), ("not_in", ["X"])):
        cond = {"field": "absent", "op": op, "value": val}
        assert evaluate_condition(cond, {}) is False


def test_evaluate_condition_transform_abs():
    cond = {"field": "z_current", "op": ">=", "value": 1.0, "transform": "abs"}
    assert evaluate_condition(cond, {"z_current": -1.5}) is True
    assert evaluate_condition(cond, {"z_current": 0.5}) is False


def test_evaluate_condition_value_field_comparison():
    cond = {"field": "h1_dir", "op": "!=", "value_field": "m5_dir"}
    assert evaluate_condition(cond, {"h1_dir": "UP", "m5_dir": "DOWN"}) is True
    assert evaluate_condition(cond, {"h1_dir": "UP", "m5_dir": "UP"}) is False


def test_evaluate_condition_unknown_operator_raises():
    with pytest.raises(PrincipleEngineError):
        evaluate_condition({"field": "f", "op": "??", "value": 1}, {"f": 1})


# ── direction / confidence ─────────────────────────────────
def test_normalize_direction_vocabulary():
    assert _normalize_direction("UP") == "haussiere"
    assert _normalize_direction("DOWN") == "baissiere"
    assert _normalize_direction("haussiere") == "haussiere"
    assert _normalize_direction("NONE") == "neutre"


def test_resolve_direction_from_field():
    emits = {"direction": "from_z_extreme_dir"}
    assert _resolve_direction(emits, {"z_extreme_dir": "UP"}) == "haussiere"
    assert _resolve_direction(emits, {"z_extreme_dir": None}) is None


def test_resolve_direction_mean_reversion_from_z():
    emits = {"direction": "mean_reversion_from_z"}
    assert _resolve_direction(emits, {"z_current": 1.8}) == "baissiere"
    assert _resolve_direction(emits, {"z_current": -1.8}) == "haussiere"
    assert _resolve_direction(emits, {"z_current": None}) is None


def test_compute_confidence_uses_bounds_proportionally():
    p = PrincipleRecord(
        principle_id="X", version=1, origin="", kind="node_rule", source_status="active",
        scope_timeframes="ALL", scope_currencies="ALL",
        bounds={"tension_score": {"min": 0.5, "max": 1.5}},
    )
    low = _compute_confidence(p, {"tension_score": 0.5})
    high = _compute_confidence(p, {"tension_score": 1.5})
    assert low == 50
    assert high == 100


def test_compute_confidence_default_without_bounds():
    p = PrincipleRecord(
        principle_id="X", version=1, origin="", kind="grammar", source_status="active",
        scope_timeframes="ALL", scope_currencies="ALL",
    )
    assert _compute_confidence(p, {}) == 60


# ── evaluate_principle (une grammaire, un contexte) ────────
def test_evaluate_principle_grammar_never_triggers():
    p = PrincipleRecord(
        principle_id="GRAMMAR_X", version=1, origin="", kind="grammar", source_status="active",
        scope_timeframes="ALL", scope_currencies="ALL", conditions=[],
    )
    result = evaluate_principle(p, {"anything": 1})
    assert result["triggered"] is False
    assert result["reason"] == "entree_documentaire_non_emettrice"


def test_evaluate_principle_node_rule_triggers_when_conditions_met():
    p = PrincipleRecord(
        principle_id="NODE_BIRTH_FAST", version=1, origin="", kind="node_rule", source_status="active",
        scope_timeframes="ALL", scope_currencies="ALL",
        conditions=[
            {"field": "state", "op": "in", "value": ["EARLY_EXTREME", "ACCUMULATING"]},
            {"field": "prev_state", "op": "==", "value": "NEUTRAL"},
            {"field": "z_current", "op": ">=", "value": 1.0, "transform": "abs"},
        ],
        emits={"direction": "mean_reversion_from_z"},
        bounds={"z_current": {"min": 1.0, "max": 2.5}},
    )
    context = {"state": "ACCUMULATING", "prev_state": "NEUTRAL", "z_current": -1.8}
    result = evaluate_principle(p, context)
    assert result["triggered"] is True
    assert result["direction"] == "haussiere"
    assert result["confidence"] is not None
    assert result["reason"] == "conditions_remplies"


def test_evaluate_principle_node_rule_fails_first_unmet_condition():
    p = PrincipleRecord(
        principle_id="X", version=1, origin="", kind="node_rule", source_status="active",
        scope_timeframes="ALL", scope_currencies="ALL",
        conditions=[
            {"field": "state", "op": "==", "value": "RUPTURE"},
            {"field": "tension_score", "op": ">=", "value": 1.0},
        ],
    )
    result = evaluate_principle(p, {"state": "PALIER"})
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:state"


# ── PrincipleEngine — intégration ─────────────────────────
def _insert_full_chain(db_path: Path, symbol: str = "EURUSD", timeframe: str = "M15") -> str:
    """Insère forces_snapshot -> scene -> behavior -> window -> exploitability
    -> zone_diagnostics (état favorable à un déclenchement node_rule)."""
    snapshot_id = f"v9-peng-{uuid.uuid4().hex[:8]}"
    forces_row = {c: None for c in FORCES_COLUMNS}
    forces_row.update({
        "snapshot_id": snapshot_id, "schema_version": "1.0",
        "timestamp": "2026-07-05T15:00:00.000Z", "source": "MT4_SDI",
        "symbol": symbol, "timeframe": timeframe, "bar_time": 1,
        "is_closed_bar": True, "mid": 1.0855,
        "force_usd": 50.0, "force_gbp": 62.0, "force_eur": 50.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "stale": False,
        "created_at": "2026-07-05T15:00:00.100Z",
    })

    scene_id = f"scene-{uuid.uuid4().hex[:8]}"
    scene_row = {c: None for c in SCENES_COLUMNS}
    scene_row.update({
        "scene_id": scene_id, "schema_version": "1.0", "timestamp": "2026-07-05T15:00:00.000Z",
        "timeframes_concernes": timeframe, "forces_snapshot_ref": snapshot_id,
        "forces_snapshot_timestamp": "2026-07-05T15:00:00.000Z",
        "coalitions_json": "[]", "antagonismes_json": "[]", "stale": False,
        "created_at": "2026-07-05T15:00:00.200Z",
    })

    behavior_id = f"beh-{uuid.uuid4().hex[:8]}"
    behavior_row = {c: None for c in BEHAVIOR_COLUMNS}
    behavior_row.update({
        "behavior_id": behavior_id, "schema_version": "1.0", "timestamp": "2026-07-05T15:00:00.000Z",
        "scene_id_ref": scene_id, "symbol": symbol, "timeframe": timeframe,
        "qualification": "bascule", "intensite": "moderee", "phase": "developpement",
        "confiance_qualification": 70, "point_de_rupture_detecte": False,
        "stale": False, "created_at": "2026-07-05T15:00:00.300Z",
    })

    window_id = f"win-{uuid.uuid4().hex[:8]}"
    window_row = {c: None for c in WINDOWS_COLUMNS}
    window_row.update({
        "window_id": window_id, "schema_version": "1.0", "timestamp": "2026-07-05T15:00:00.000Z",
        "behavior_id": behavior_id, "behavior_qualification": "bascule", "behavior_confiance": 70,
        "statut": "ouverte", "type_fenetre": "retournement", "niveau_confiance": 70,
        "fragilite_detectee": False, "conditions_invalidation_json": "[]", "stale": False,
        "created_at": "2026-07-05T15:00:00.400Z",
    })

    exploitability_id = f"exp-{uuid.uuid4().hex[:8]}"
    exploitability_row = {c: None for c in EXPLOITABILITY_COLUMNS}
    exploitability_row.update({
        "exploitability_id": exploitability_id, "schema_version": "1.0",
        "timestamp": "2026-07-05T15:00:00.000Z", "window_id": window_id,
        "window_statut": "ouverte", "window_niveau_confiance": 70,
        "statut": "exploitable", "niveau_confiance_global": 78,
        "validation_hitl_requise": True, "replay_nombre_cas": 0,
        "stale": False, "created_at": "2026-07-05T15:00:00.500Z",
    })

    zone_gbp = {c: None for c in ZONE_DIAGNOSTICS_COLUMNS}
    zone_gbp.update({
        "zone_diagnostic_id": f"zone-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
        "timestamp": "2026-07-05T15:00:00.000Z", "forces_snapshot_ref": snapshot_id,
        "symbol": symbol, "timeframe": timeframe, "currency": "GBP",
        "state": "ACCUMULATING", "prev_state": "NEUTRAL",
        "z_current": -1.8, "z_extreme_dir": "DOWN", "bars_in_extreme": 1,
        "absorbed_pullback_count": 2, "tension_score": 1.2,
        "stale": False, "created_at": "2026-07-05T15:00:00.600Z",
    })

    init_scene_db(db_path)
    init_behavior_db(db_path)
    init_window_db(db_path)
    init_exploitability_db(db_path)
    init_regime_db(db_path)
    init_zone_db(db_path)

    conn = get_connection(db_path)
    try:
        conn.execute(
            f"INSERT INTO forces_snapshots ({', '.join(FORCES_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(FORCES_COLUMNS))})",
            [forces_row[c] for c in FORCES_COLUMNS],
        )
        conn.execute(
            f"INSERT INTO scenes ({', '.join(SCENES_COLUMNS)}) VALUES ({', '.join(['?'] * len(SCENES_COLUMNS))})",
            [scene_row[c] for c in SCENES_COLUMNS],
        )
        conn.execute(
            f"INSERT INTO behaviors ({', '.join(BEHAVIOR_COLUMNS)}) VALUES ({', '.join(['?'] * len(BEHAVIOR_COLUMNS))})",
            [behavior_row[c] for c in BEHAVIOR_COLUMNS],
        )
        conn.execute(
            f"INSERT INTO windows ({', '.join(WINDOWS_COLUMNS)}) VALUES ({', '.join(['?'] * len(WINDOWS_COLUMNS))})",
            [window_row[c] for c in WINDOWS_COLUMNS],
        )
        conn.execute(
            f"INSERT INTO exploitability ({', '.join(EXPLOITABILITY_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(EXPLOITABILITY_COLUMNS))})",
            [exploitability_row[c] for c in EXPLOITABILITY_COLUMNS],
        )
        conn.execute(
            f"INSERT INTO zone_diagnostics ({', '.join(ZONE_DIAGNOSTICS_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(ZONE_DIAGNOSTICS_COLUMNS))})",
            [zone_gbp[c] for c in ZONE_DIAGNOSTICS_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()
    return snapshot_id


def test_engine_syncs_principles_table(db_path: Path):
    PrincipleEngine(db_path=db_path)
    conn = get_connection(db_path)
    try:
        n = conn.execute("SELECT COUNT(*) FROM principles").fetchone()[0]
        n_active = conn.execute(
            "SELECT COUNT(*) FROM principles WHERE v9_status = 'ACTIVE'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == 27
    assert n_active == 10


def test_evaluate_principles_missing_snapshot_raises(db_path: Path):
    engine = PrincipleEngine(db_path=db_path)
    with pytest.raises(PrincipleEngineError):
        engine.evaluate_principles("does-not-exist")


def test_evaluate_principles_triggers_node_rule_with_zone_diagnostics(db_path: Path):
    snapshot_id = _insert_full_chain(db_path, timeframe="M15")
    engine = PrincipleEngine(db_path=db_path)
    evaluations = engine.evaluate_principles(snapshot_id)
    gbp_triggered = [
        e for e in evaluations
        if e["currency"] == "GBP" and e["principle_id"] == "NODE_BIRTH_FAST" and e["triggered"]
    ]
    assert gbp_triggered, "NODE_BIRTH_FAST devrait se déclencher avec ce contexte zone_diagnostics"
    assert gbp_triggered[0]["direction"] == "haussiere"

    conn = get_connection(db_path)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM principle_evaluations WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == len(evaluations)
    assert n > 0


def test_evaluate_principles_restricts_by_timeframe_scope(db_path: Path):
    snapshot_id = _insert_full_chain(db_path, timeframe="M30")
    engine = PrincipleEngine(db_path=db_path)
    evaluations = engine.evaluate_principles(snapshot_id)
    node_rule_evals = [e for e in evaluations if e["kind"] == "node_rule"]
    assert node_rule_evals == [], "les 7 node_rule sont scopés a M5/M15/H1/H4, jamais M30"
    grammar_evals = [e for e in evaluations if e["kind"] == "grammar"]
    assert len(grammar_evals) == 18 * len(DEVISES)


def test_evaluate_principles_without_zone_diagnostics_never_triggers_node_rule(db_path: Path):
    snapshot_id = _insert_full_chain(db_path, timeframe="H1")
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM zone_diagnostics")
        conn.commit()
    finally:
        conn.close()

    engine = PrincipleEngine(db_path=db_path)
    evaluations = engine.evaluate_principles(snapshot_id)
    node_rule_triggered = [e for e in evaluations if e["kind"] == "node_rule" and e["triggered"]]
    assert node_rule_triggered == []


def test_evaluate_principles_performance_under_target(db_path: Path):
    import time

    snapshot_id = _insert_full_chain(db_path, timeframe="H1")
    engine = PrincipleEngine(db_path=db_path)
    t0 = time.perf_counter()
    engine.evaluate_principles(snapshot_id)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 200

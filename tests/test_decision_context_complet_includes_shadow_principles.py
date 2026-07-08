"""Test unitaire — contexte_complet_json inclut la trace complète des
principes évalués, y compris ceux non-déclenchés / non-ACTIVE (Phase C4
doctrine realign). Verrouille le comportement déjà présent avant C1
(DecisionLogger._load_principles ne filtre ni sur v9_status ni sur
triggered) pour garantir qu'il survit au passage de PRINCIPLE_ACTIVE_IDS
de 10 à 27 principes."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from core.v9.decision_logger import DecisionLogger
from core.v9.principle_db import PRINCIPLE_EVALUATIONS_COLUMNS
from tests.test_decision_logger import _insert_row, build_full_chain, db_path  # noqa: F401


def _insert_extra_principle_eval(
    db_path: Path, snapshot_id: str, principle_id: str, v9_status: str, triggered: bool
) -> None:
    row = {c: None for c in PRINCIPLE_EVALUATIONS_COLUMNS}
    row.update({
        "evaluation_id": f"peval-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
        "timestamp": "2026-07-05T17:00:00.000Z", "snapshot_id": snapshot_id,
        "principle_id": principle_id, "v9_status": v9_status, "kind": "grammar",
        "symbol": "GBPUSD", "timeframe": "M15", "currency": "GBP",
        "triggered": triggered, "direction": None, "confidence": None,
        "anti_signal_bias": False,
        "reason": "conditions_remplies" if triggered else "entree_documentaire_non_emettrice",
        "context_json": "{}", "created_at": "2026-07-05T17:00:00.700Z",
    })
    _insert_row(db_path, "principle_evaluations", PRINCIPLE_EVALUATIONS_COLUMNS, row)


def test_contexte_complet_includes_non_triggered_and_shadow_evaluations(db_path: Path):
    snapshot_id = build_full_chain(db_path)  # insère déjà ZONE_RETEST ACTIVE/triggered
    _insert_extra_principle_eval(db_path, snapshot_id, "GRAMMAR_ABSORPTION", "SHADOW", False)
    _insert_extra_principle_eval(db_path, snapshot_id, "GRAMMAR_TENSION", "ACTIVE", False)

    decision = DecisionLogger(db_path=db_path).log(snapshot_id)

    principle_ids_in_trace = {
        p["principle_id"] for p in decision["contexte_complet"]["principle_evaluations"]
    }
    assert principle_ids_in_trace == {"ZONE_RETEST", "GRAMMAR_ABSORPTION", "GRAMMAR_TENSION"}

    # Le champ "principes" (source du signal) reste, lui, restreint aux
    # seuls principes ayant réellement contribué au vote — pas de confusion
    # entre la trace complète (contexte_complet) et la source du signal.
    assert decision["principes"] == ["ZONE_RETEST"]


def test_contexte_complet_json_round_trips_all_evaluations(db_path: Path):
    snapshot_id = build_full_chain(db_path)
    _insert_extra_principle_eval(db_path, snapshot_id, "GRAMMAR_SQUEEZE", "SHADOW", False)

    decision = DecisionLogger(db_path=db_path).log(snapshot_id)

    contexte_complet_json = json.dumps(
        decision["contexte_complet"], ensure_ascii=False, default=str
    )
    reloaded = json.loads(contexte_complet_json)
    assert len(reloaded["principle_evaluations"]) == 2

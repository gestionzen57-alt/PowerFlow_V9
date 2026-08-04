"""REGISTRY.py — registre statique des agents Mode A V9 → V10.

5 agents chauds (cœur cognitif) + 1 superviseur (déjà livré scripts/v9_supervisor.py)
+ 1 reviewer latéral (Telegram). Aucun appel LLM dans la boucle (règle 18).

But : donner un point d'isolation par couche + un contrat I/O vérifiable.
Anti-fédération V8 : pas de RPC, pas de bus, pas de multi-process.

Format d'entrée : dict conforme au schema_version de l'agent.
Format de sortie : dict conforme au schema_version de l'agent.

Sprint 2026-07-07 — Hermes autonomous sprint.
V10 doctrine (2026-08-04) : 30 règles V9 → 10 règles R1-R10. Hérité V9
conservé (core/v9/, scripts/v9_*.py, capture port 31685, R10 sécurité).
V10 ajoute 7 modules intelligents : M0 Marché, M1 Capture, M2 Contexte
(TA lecture CEO), M3 Alertes+Exec, M4 Décision (CoT 5 étapes),
M5 Optimisation (Bayesian+Genetic), M6 Apprentissage (Online RL),
M7 Réflexion (Self-explanation). Voir `V10_TRANSITION_NOTICE.md` +
`docs/V10/V10_PLAN_REPARALETTRAGE.md`.
"""
from __future__ import annotations

from typing import Any

REGISTRY: dict[str, dict[str, Any]] = {
    "force_reader": {
        "name": "force_reader",
        "module": "core.v9.forces_reader",
        "class": "ForcesReader",
        "method": "transform",
        "input_schema": "raw_forces_dict_v1",
        "output_schema": "transformed_row_v1",
        "blocking": True,
        "couche": 2,
        "group": "cognitive",
    },
    "scene_builder": {
        "name": "scene_builder",
        "module": "core.v9.scene_builder",
        "class": "SceneBuilder",
        "method": "build_scene",
        "input_schema": "snapshot_id_v1",
        "output_schema": "scene_dict_v1",
        "blocking": True,
        "couche": 3,
        "group": "cognitive",
    },
    "behavior_analyst": {
        "name": "behavior_analyst",
        "module": "core.v9.behavior_analyzer",
        "class": "BehaviorAnalyzer",
        "method": "analyze_scene",
        "input_schema": "scene_id_v1",
        "output_schema": "behavior_dict_v1",
        "blocking": True,
        "couche": 4,
        "group": "cognitive",
    },
    "gatekeeper": {
        "name": "gatekeeper",
        "module": "core.v9.orchestrator",
        "function": "_gatekeeper_run",
        "input_schema": "behavior_id_v1",
        "output_schema": "gate_result_v1",
        "blocking": True,
        "couche": 5,
        "group": "cognitive",
        "note": "Fusion window_gate + exploitability_evaluator + regime_detector",
    },
    "decision_maker": {
        "name": "decision_maker",
        "module": "core.v9.orchestrator",
        "function": "_decision_maker_run",
        "input_schema": "snapshot_id_v1",
        "output_schema": "decision_dict_v1",
        "blocking": True,
        "couche": 8,
        "group": "cognitive",
        "note": "Fusion principle_engine + signal_generator + decision_logger",
    },
    "supervisor": {
        "name": "supervisor",
        "module": "scripts.v9_supervisor",
        "class": "V9Supervisor",
        "blocking": True,
        "group": "meta",
        "note": "déjà livré (scripts/v9_supervisor.py)",
    },
    "reviewer": {
        "name": "reviewer",
        "module": "scripts.v9_telegram_notifier",
        "blocking": False,
        "group": "meta",
        "note": "HITL Telegram, fire-and-forget (déjà livré)",
    },
}


def get(name: str) -> dict[str, Any] | None:
    return REGISTRY.get(name)


def list_agents(group: str | None = None) -> list[str]:
    if group is None:
        return list(REGISTRY.keys())
    return [k for k, v in REGISTRY.items() if v.get("group") == group]


def list_cognitifs() -> list[str]:
    return list_agents("cognitive")

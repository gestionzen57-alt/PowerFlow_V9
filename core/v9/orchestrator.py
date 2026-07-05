"""orchestrator.py — Déclenche la chaîne cognitive complète après capture.

Chaîne cognitive officielle :
    Forces → [ORCHESTRATEUR] → Scènes → Comportements → Fenêtres → Exploitabilité

Appelé par capture_server.py après chaque insertion non-stale dans
forces_snapshots. Fait traverser le snapshot par les 4 couches avales, dans
l'ordre, en persistant chaque résultat dans sa table (`scenes`, `behaviors`,
`windows`, `exploitability`). N'importe quelle étape peut échouer : la
chaîne s'arrête à cette étape, l'erreur est loggée, mais l'appelant ne doit
jamais planter (le serveur de capture doit continuer à recevoir des
snapshots).

Aucune logique de trading, aucune décision — cette couche ne fait
qu'enchaîner les couches déjà validées en replay (Phase 8).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from core.v9.behavior_analyzer import BehaviorAnalyzer
from core.v9.config import DB_PATH, ROOT_DIR
from core.v9.exploitability_evaluator import ExploitabilityEvaluator
from core.v9.scene_builder import SceneBuilder
from core.v9.window_gate import WindowGate

log = logging.getLogger("v9.orchestrator")

DEFAULT_MEMORY_DIR = ROOT_DIR / "memory"


def run_chain(
    snapshot_id: str,
    db_path: Path | None = None,
    memory_dir: Path | None = None,
) -> dict:
    """Fait traverser un snapshot par Scènes -> Comportements -> Fenêtres -> Exploitabilité.

    Retourne un dict avec l'id produit à chaque étape atteinte (`scene_id`,
    `behavior_id`, `window_id`, `exploitability_id`) et `error` (nom de la
    couche en échec, ou None si la chaîne est allée à son terme).
    """
    db_path = db_path or DB_PATH
    memory_dir = memory_dir or DEFAULT_MEMORY_DIR

    result: dict = {
        "snapshot_id": snapshot_id,
        "scene_id": None,
        "behavior_id": None,
        "window_id": None,
        "exploitability_id": None,
        "error": None,
    }

    try:
        t0 = time.perf_counter()
        scene_builder = SceneBuilder(db_path=db_path, config={"memory_dir": memory_dir})
        scene = scene_builder.build_scene(snapshot_id)
        scene_builder._write_scene_to_db(scene)
        result["scene_id"] = scene["scene_id"]
        log.info(
            "scene_builder: %s -> %s (%.1fms)",
            snapshot_id, scene["scene_id"], (time.perf_counter() - t0) * 1000,
        )
    except Exception:
        log.exception("orchestrator: echec scene_builder[%s]", snapshot_id)
        result["error"] = "scene_builder"
        return result

    try:
        t0 = time.perf_counter()
        behavior_analyzer = BehaviorAnalyzer(db_path=db_path, config={"memory_dir": memory_dir})
        behavior = behavior_analyzer.analyze_scene(scene["scene_id"])
        result["behavior_id"] = behavior["behavior_id"]
        log.info(
            "behavior_analyzer: %s -> %s (%.1fms)",
            scene["scene_id"], behavior["behavior_id"], (time.perf_counter() - t0) * 1000,
        )
    except Exception:
        log.exception("orchestrator: echec behavior_analyzer[%s]", scene["scene_id"])
        result["error"] = "behavior_analyzer"
        return result

    try:
        t0 = time.perf_counter()
        window_gate = WindowGate(db_path=db_path, memory_path=memory_dir / "memory_temp.md")
        window = window_gate.evaluate_behavior(behavior["behavior_id"])
        result["window_id"] = window["window_id"]
        log.info(
            "window_gate: %s -> %s statut=%s (%.1fms)",
            behavior["behavior_id"], window["window_id"], window["statut"],
            (time.perf_counter() - t0) * 1000,
        )
    except Exception:
        log.exception("orchestrator: echec window_gate[%s]", behavior["behavior_id"])
        result["error"] = "window_gate"
        return result

    try:
        t0 = time.perf_counter()
        evaluator = ExploitabilityEvaluator(db_path=db_path, config={"memory_dir": memory_dir})
        evaluation = evaluator.evaluate_window(window["window_id"])
        result["exploitability_id"] = evaluation["exploitability_id"]
        log.info(
            "exploitability_evaluator: %s -> %s statut=%s (%.1fms)",
            window["window_id"], evaluation["exploitability_id"], evaluation["statut"],
            (time.perf_counter() - t0) * 1000,
        )
    except Exception:
        log.exception("orchestrator: echec exploitability_evaluator[%s]", window["window_id"])
        result["error"] = "exploitability_evaluator"
        return result

    return result

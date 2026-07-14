"""orchestrator.py — Déclenche la chaîne cognitive complète après capture.

Chaîne cognitive officielle :
    Forces → [ORCHESTRATEUR] → Scènes → Comportements → Fenêtres →
    Exploitabilité → Régime → Principes → Signal → Décision

Appelé par capture_server.py après chaque insertion non-stale dans
forces_snapshots. Fait traverser le snapshot par les couches avales, dans
l'ordre, en persistant chaque résultat dans sa table (`scenes`, `behaviors`,
`windows`, `exploitability`, `regime_snapshots`, `principle_evaluations`,
`signals`, `decisions`). N'importe quelle étape peut échouer : la
chaîne s'arrête à cette étape, l'erreur est loggée, mais l'appelant ne doit
jamais planter (le serveur de capture doit continuer à recevoir des
snapshots).

Phase 9 ajoute la couche Décision (régime -> principes -> signal ->
décision) après Exploitabilité. Cette couche ne fait qu'agréger des
lectures déjà validées par les couches amont ; `decisions.action` est une
recommandation qualitative, jamais un ordre — aucune logique d'exécution.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from core.v9.behavior_analyzer import BehaviorAnalyzer
from core.v9.config import DB_PATH, ROOT_DIR
from core.v9.decision_logger import DecisionLogger
from core.v9.exploitability_evaluator import ExploitabilityEvaluator
from core.v9 import flow_probe
from core.v9.principle_engine import PrincipleEngine
from core.v9.regime_detector import RegimeDetector
from core.v9.scene_builder import SceneBuilder
from core.v9.signal_generator import SignalGenerator
from core.v9.window_gate import WindowGate
from core.v9.zone_detector import ZoneDetector

log = logging.getLogger("v9.orchestrator")

DEFAULT_MEMORY_DIR = ROOT_DIR / "memory"


def run_chain(
    snapshot_id: str,
    db_path: Path | None = None,
    memory_dir: Path | None = None,
    source_type: str = "live",
) -> dict:
    """Fait traverser un snapshot par Scènes -> Comportements -> Fenêtres ->
    Exploitabilité -> Régime -> Principes -> Signal -> Décision.

    Retourne un dict avec l'id produit à chaque étape atteinte (`scene_id`,
    `behavior_id`, `window_id`, `exploitability_id`, `signal_id`,
    `decision_id`) et `error` (nom de la couche en échec, ou None si la
    chaîne est allée à son terme).

    Args:
        source_type: "live" pour la capture temps réel, "replay" pour la régénération.
    """
    db_path = db_path or DB_PATH
    memory_dir = memory_dir or DEFAULT_MEMORY_DIR

    result: dict = {
        "snapshot_id": snapshot_id,
        "scene_id": None,
        "behavior_id": None,
        "window_id": None,
        "exploitability_id": None,
        "signal_id": None,
        "decision_id": None,
        "error": None,
    }
    t_chain_start = time.perf_counter()

    def _probe(status: str) -> None:
        try:
            flow_probe.record(
                snapshot_id,
                "chain",
                status=status,
                record_id=result.get("decision_id") or result.get("signal_id"),
                latency_ms=(time.perf_counter() - t_chain_start) * 1000,
                db_path=db_path,
            )
        except Exception:
            log.debug("orchestrator: flow_probe.record best-effort echec[%s]", snapshot_id, exc_info=True)

    try:
        t0 = time.perf_counter()
        scene_builder = SceneBuilder(db_path=db_path, config={"memory_dir": memory_dir, "source_type": source_type})
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
        _probe("ERROR:scene_builder")
        return result

    try:
        t0 = time.perf_counter()
        behavior_analyzer = BehaviorAnalyzer(db_path=db_path, config={"memory_dir": memory_dir, "source_type": source_type})
        behavior = behavior_analyzer.analyze_scene(scene["scene_id"])
        result["behavior_id"] = behavior["behavior_id"]
        log.info(
            "behavior_analyzer: %s -> %s (%.1fms)",
            scene["scene_id"], behavior["behavior_id"], (time.perf_counter() - t0) * 1000,
        )
    except Exception:
        log.exception("orchestrator: echec behavior_analyzer[%s]", scene["scene_id"])
        result["error"] = "behavior_analyzer"
        _probe("ERROR:behavior_analyzer")
        return result

    try:
        t0 = time.perf_counter()
        window_gate = WindowGate(db_path=db_path, memory_path=memory_dir / "memory_temp.md", source_type=source_type)
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
        _probe("ERROR:window_gate")
        return result

    try:
        t0 = time.perf_counter()
        evaluator = ExploitabilityEvaluator(db_path=db_path, config={"memory_dir": memory_dir, "source_type": source_type})
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
        _probe("ERROR:exploitability_evaluator")
        return result

    try:
        t0 = time.perf_counter()
        regime_detector = RegimeDetector(db_path=db_path, source_type=source_type)
        regime_detector.detect(snapshot_id)
        log.info("regime_detector: %s (%.1fms)", snapshot_id, (time.perf_counter() - t0) * 1000)
    except Exception:
        log.exception("orchestrator: echec regime_detector[%s]", snapshot_id)
        result["error"] = "regime_detector"
        _probe("ERROR:regime_detector")
        return result

    try:
        t0 = time.perf_counter()
        # Phase 14a — Kill switch données mortes (CEO Søn backlog 2026-07-08).
        # ROI : -25% DB si activé (zone_diagnostics jamais consommé downstream).
        # Défaut False = comportement actuel préservé.
        import os as _os
        if not _os.environ.get("V9_DISABLE_ZONE_DIAGNOSTICS"):
            zone_detector = ZoneDetector(db_path=db_path, source_type=source_type)
            zone_detector.detect(snapshot_id)
            log.info("zone_detector: %s (%.1fms)", snapshot_id, (time.perf_counter() - t0) * 1000)
        else:
            log.debug("zone_detector: SKIPPED via V9_DISABLE_ZONE_DIAGNOSTICS [%s]", snapshot_id)
    except Exception:
        log.exception("orchestrator: echec zone_detector[%s]", snapshot_id)
        result["error"] = "zone_detector"
        _probe("ERROR:zone_detector")
        return result

    try:
        t0 = time.perf_counter()
        principle_engine = PrincipleEngine(db_path=db_path, source_type=source_type)
        principle_engine.evaluate_principles(snapshot_id)
        log.info("principle_engine: %s (%.1fms)", snapshot_id, (time.perf_counter() - t0) * 1000)
    except Exception:
        log.exception("orchestrator: echec principle_engine[%s]", snapshot_id)
        result["error"] = "principle_engine"
        _probe("ERROR:principle_engine")
        return result

    try:
        t0 = time.perf_counter()
        signal_generator = SignalGenerator(db_path=db_path, source_type=source_type)
        signal = signal_generator.generate(snapshot_id)
        result["signal_id"] = signal["signal_id"]
        log.info(
            "signal_generator: %s -> %s direction=%s (%.1fms)",
            snapshot_id, signal["signal_id"], signal["direction"],
            (time.perf_counter() - t0) * 1000,
        )
    except Exception:
        log.exception("orchestrator: echec signal_generator[%s]", snapshot_id)
        result["error"] = "signal_generator"
        _probe("ERROR:signal_generator")
        return result

    try:
        t0 = time.perf_counter()
        decision_logger = DecisionLogger(db_path=db_path, source_type=source_type)
        decision = decision_logger.log(snapshot_id)
        result["decision_id"] = decision["decision_id"]
        log.info(
            "decision_logger: %s -> %s action=%s (%.1fms)",
            snapshot_id, decision["decision_id"], decision["action"],
            (time.perf_counter() - t0) * 1000,
        )
    except Exception:
        log.exception("orchestrator: echec decision_logger[%s]", snapshot_id)
        result["error"] = "decision_logger"
        _probe("ERROR:decision_logger")
        return result

    # ── P2 — shadow mode (hook non-bloquant) ──
    # Rejoue principes -> signal -> décision avec les kill switches
    # expérimentaux activés (cf core/v9/shadow_evaluator.py), tagué
    # source_type="shadow", pour comparer au résultat live sans jamais
    # le modifier. Kill switch dédié V9_SHADOW_MODE_ENABLED, OFF par
    # défaut (R25') — inactif tant que Søn ne l'active pas explicitement.
    # Zéro appel réseau ici (R18) : toute alerte de divergence est un
    # script séparé, hors du chemin cognitif.
    if _shadow_mode_enabled():
        try:
            t2 = time.perf_counter()
            from core.v9.shadow_evaluator import run_shadow_pass
            run_shadow_pass(snapshot_id, db_path=db_path)
            log.info(
                "shadow_evaluator: %s (%.1fms)",
                snapshot_id, (time.perf_counter() - t2) * 1000,
            )
        except Exception:  # noqa: BLE001
            # Ne JAMAIS bloquer l'orchestrator à cause du shadow pass.
            log.exception("orchestrator: shadow_evaluator failed (non-blocking)")

    # ── Phase 9.10 — auto-resolve WIN/LOSS (hook non-bloquant) ──
    # Appelé après chaque décision. Ne tourne que si
    # `auto_resolve_enabled = True` (par défaut, désactivable via env).
    # Si ça plante, l'orchestrator continue — le daemon séparé assure
    # quand même la résolution en arrière-plan.
    if _auto_resolve_enabled():
        try:
            t1 = time.perf_counter()
            n_resolved = _auto_resolve_old_decisions(
                db_path=db_path,
                min_age_hours=24.0,
                horizon_hours=4.0,
                batch_limit=50,  # max par cycle pour ne pas bloquer l'orch
            )
            if n_resolved > 0:
                log.info(
                    "auto_resolve: %d décisions résolues (%.0fms)",
                    n_resolved, (time.perf_counter() - t1) * 1000,
                )
        except Exception:  # noqa: BLE001
            # Ne JAMAIS bloquer l'orchestrator à cause du resolver
            log.exception("orchestrator: auto_resolve failed (non-blocking)")

    _probe("OK")
    return result


# ── Phase 9.10 — auto-resolve WIN/LOSS ─────────────────────────
import os  # noqa: E402

_AUTO_RESOLVE_ENV = "V9_AUTO_RESOLVE_ENABLED"

# ── P2 — shadow mode ────────────────────────────────────────────
_SHADOW_MODE_ENV = "V9_SHADOW_MODE_ENABLED"


def _shadow_mode_enabled() -> bool:
    """Kill switch V9_SHADOW_MODE_ENABLED (défaut '0' = OFF, R25').
    Mettre à '1' pour activer le hook shadow sans modifier le code."""
    return os.environ.get(_SHADOW_MODE_ENV, "0") == "1"


def _auto_resolve_enabled() -> bool:
    """Active/désactive le hook auto_resolve dans l'orchestrator.
    Lit l'env var V9_AUTO_RESOLVE_ENABLED (défaut '1' = ON).
    Mettre à '0' pour désactiver sans modifier le code."""
    return os.environ.get(_AUTO_RESOLVE_ENV, "1") != "0"


def _auto_resolve_old_decisions(
    db_path: Path,
    min_age_hours: float,
    horizon_hours: float,
    batch_limit: int,
) -> int:
    """Hook appelé en fin de cycle orchestrator. Délègue à
    `scripts.v9_resolve_decision_auto.run()` puis applique les
    résolutions. Limite batch pour ne pas étirer le cycle orch.

    Retourne le nombre de décisions résolues. 0 si rien à faire.
    """
    # Import local pour éviter circularité et coût au démarrage orchestrator
    from scripts.v9_resolve_decision_auto import (  # noqa: PLC0415
        _connect as _res_connect,
        _ensure_perf_index,
        DEFAULT_HORIZON_HOURS,
        DEFAULT_SKIP_SESSIONS,
        apply_resolutions,
        resolve_one,
    )
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    # Brief O1 (2026-07-12) : le hook live doit suivre le même défaut que le
    # CLI (DYNAMIC + skip new_york/after) — sinon le fil de l'eau live
    # résoudrait ces sessions directionnellement malgré leur WR défavorable.
    skip_sessions = [s.strip() for s in DEFAULT_SKIP_SESSIONS.split(",") if s.strip()]

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=min_age_hours)).isoformat()
    conn = _res_connect(db_path)
    try:
        _ensure_perf_index(conn)
        # Sélectionner les N plus anciennes décisions non résolues
        rows = conn.execute(
            "SELECT decision_id, timestamp, symbol, timeframe, direction, "
            "       snapshot_id, confiance "
            "FROM decisions "
            "WHERE action='preparer_entree' AND is_win IS NULL "
            "AND timestamp IS NOT NULL AND timestamp < ? "
            "ORDER BY timestamp ASC LIMIT ?",
            (cutoff, batch_limit),
        ).fetchall()
        if not rows:
            return 0
        resolutions = []
        for dec in rows:
            r = resolve_one(
                conn, dec, horizon_hours=horizon_hours, skip_no_future=True,
                skip_sessions=skip_sessions,
            )
            resolutions.append(r)
        to_apply = [r for r in resolutions if r["resolved"]]
        if not to_apply:
            return 0
        return apply_resolutions(conn, to_apply)
    finally:
        conn.close()

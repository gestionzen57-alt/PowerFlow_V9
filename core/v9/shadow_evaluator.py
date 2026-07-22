"""shadow_evaluator.py — P2 Shadow mode, volet évaluation (2026-07-13).

Rejoue la queue cognitive tardive (principes -> signal -> décision) pour un
snapshot déjà traité en live, avec un jeu de kill switches expérimentaux
activés, afin de comparer le résultat "shadow" au résultat "live" sans
jamais toucher aux données live. Objectif : évaluer des chantiers gated
(P3-WIRE adaptive thresholds, etc.) sur du flux réel avant toute décision
d'activation, sans risque sur le pipeline live (cf STATE.md §5.2 P2).

Périmètre volontairement restreint — ne rejoue PAS :
- scene_builder / behavior_analyzer / window_gate / exploitability_evaluator
  / regime_detector / zone_detector. Ces couches sont perceptuelles
  (immobiles depuis Phase 9.9, STATE.md §3.1), ne portent aucun kill switch
  expérimental, et `regime_snapshots` / `zone_diagnostics` utilisent
  `INSERT OR REPLACE` avec une contrainte UNIQUE (snapshot, currency) : un
  second `detect()` sur un snapshot déjà traité en live écraserait
  silencieusement la ligne live (corruption de données perceptuelles).
  Le shadow réutilise donc les lectures live déjà en base —
  `PrincipleEngine._load_shared_context` interroge par `snapshot_id`, pas
  par `source_type`.
- Le shadow rejoue PrincipleEngine.evaluate_principles + SignalGenerator.
  generate + une décision, tagués `source_type="shadow"`. `signals`/
  `principle_evaluations` ne portent de contrainte UNIQUE que sur leur id
  aléatoire propre — duplication sans risque. `decisions` en revanche
  calcule un `decision_id` **déterministe par snapshot_id**
  (`_decision_id_for_snapshot`, fix 2026-07-06 anti-duplication réplay) et
  écrit en `INSERT OR REPLACE` : un second `.log()` sur le même snapshot
  écraserait silencieusement la décision live. `ShadowDecisionLogger`
  neutralise ce risque en faisant calculer un `decision_id` namespacé
  `dec_shadow_*` (monkeypatch scopé, restauré en `finally`, jamais de
  modification de `decision_logger.py`) — la décision shadow coexiste
  toujours avec la décision live, jamais ne l'écrase.
- `ShadowDecisionLogger` neutralise aussi le branchement HITL Telegram
  (`DecisionLogger._apply_hitl_branching`, Brief O3) : une décision shadow
  ne doit jamais déclencher une notification qui ressemblerait à un signal
  live low-confidence.
- Zéro appel réseau ici (R18). Toute alerte de divergence shadow/live est
  un chantier séparé et hors du chemin cognitif
  (`scripts/v9_shadow_divergence_report.py`), jamais dans ce module ni
  dans `orchestrator.py`.

Kill switch maître : `V9_SHADOW_MODE_ENABLED` (défaut '0' = OFF, R25').
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9 import decision_logger as decision_logger_module
from core.v9.decision_db import DECISIONS_COLUMNS
from core.v9.decision_logger import DecisionLogger, _compress_json
from core.v9.principle_engine import PrincipleEngine
from core.v9.signal_generator import SignalGenerator

logger = logging.getLogger("v9.shadow_evaluator")

SHADOW_MODE_ENV = "V9_SHADOW_MODE_ENABLED"
SOURCE_TYPE_SHADOW = "shadow"

# Kill switches expérimentaux évalués en shadow — jamais actifs en live
# tant que Søn ne les active pas explicitement (R25'). Chantiers gated
# prêts à être évalués en double-aveugle :
# - P3-WIRE : adaptive thresholds (descriptif, aucun YAML ne consomme)
# - A1 (trader_mini) : weighter baseline Brief Q1
# - A2 (auto_calibrator) : recalibrage propose-only Brief Q2
# Note 2026-07-14 : A1 et A2 sont activés globalement (motion CEO),
# mais leur présence dans SHADOW_ENV_OVERRIDES garantit qu'un shadow
# pass les évalue même si un opérateur les désactive temporairement.
SHADOW_ENV_OVERRIDES: dict[str, str] = {
    "V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED": "1",
    "V9_TRADER_MINI_ENABLED": "1",
    "V9_AUTO_CALIBRATOR_ENABLED": "1",
}


def is_shadow_mode_enabled() -> bool:
    """Kill switch V9_SHADOW_MODE_ENABLED (défaut '0' = OFF)."""
    return os.environ.get(SHADOW_MODE_ENV, "0") == "1"


def _shadow_decision_id_for_snapshot(snapshot_id: str) -> str:
    """decision_id shadow, namespacé distinctement du decision_id live.

    `DecisionLogger._decision_id_for_snapshot` est déterministe par
    snapshot_id SEUL (pas par source_type) — deux appels `.log()` sur le
    même snapshot produisent le MÊME decision_id, et `INSERT OR REPLACE`
    écraserait la décision live. Ce namespace `"shadow:"` évite toute
    collision, tout en restant déterministe (rejouer le shadow sur le
    même snapshot remplace seulement la ligne shadow, jamais la live)."""
    short = uuid.uuid5(uuid.NAMESPACE_URL, f"shadow:{snapshot_id}").hex[:12]
    return f"dec_shadow_{short}"


class ShadowDecisionLogger(DecisionLogger):
    """DecisionLogger sans risque de collision decision_id ni branchement
    HITL Telegram.

    - `_apply_hitl_branching` : toujours `low_confidence_block=0` — une
      décision shadow ne doit jamais produire de notification qui
      ressemblerait à un signal live (Brief O3).
    - `log()` : fait calculer un decision_id namespacé `dec_shadow_*` par
      monkeypatch scopé de `decision_logger._decision_id_for_snapshot`
      (jamais de modification de `decision_logger.py` — restauré dans un
      `finally`, y compris si `.log()` lève)."""

    def _apply_hitl_branching(
        self,
        direction: str | None,
        confiance: int | None,
        symbol: str,
        timeframe: str,
        principes: list[str],
    ) -> int:
        return 0

    def _write_to_db(self, conn: sqlite3.Connection, decision: dict) -> None:
        """Écriture directe, sans pré-check qualité.

        Le pré-check qualité de DecisionLogger._write_to_db cherche par
        snapshot_id sans filtre source_type : il trouve la décision live
        (même snapshot_id), compare les qualités, et skip l'écriture si
        la qualité shadow n'est pas strictement supérieure — ce qui est
        toujours le cas (shadow et live partagent le même snapshot, donc
        la même qualité). Résultat : la décision shadow n'est jamais écrite.

        ShadowDecisionLogger a un decision_id namespacé `dec_shadow_*`
        (cf. _shadow_decision_id_for_snapshot), donc INSERT OR REPLACE
        ne peut pas collisionner avec la décision live. On saute le
        pré-check et on écrit directement.
        """
        now = datetime.now(timezone.utc).isoformat()
        values = {
            **decision,
            "principes_json": json.dumps(decision["principes"], ensure_ascii=False),
            "contexte_complet_json": _compress_json(decision["contexte_complet"]),
            "created_at": now,
        }
        columns = ", ".join(DECISIONS_COLUMNS)
        placeholders = ", ".join("?" for _ in DECISIONS_COLUMNS)
        conn.execute(
            f"INSERT OR REPLACE INTO decisions ({columns}) VALUES ({placeholders})",
            [values.get(c) for c in DECISIONS_COLUMNS],
        )
        conn.commit()

    def log(self, snapshot_id: str) -> dict[str, Any]:
        original = decision_logger_module._decision_id_for_snapshot
        decision_logger_module._decision_id_for_snapshot = _shadow_decision_id_for_snapshot
        try:
            return super().log(snapshot_id)
        finally:
            decision_logger_module._decision_id_for_snapshot = original


def run_shadow_pass(
    snapshot_id: str,
    *,
    db_path: Path | None = None,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Rejoue principes -> signal -> décision pour `snapshot_id` avec les
    kill switches expérimentaux temporairement activés, tagué
    `source_type="shadow"`.

    Restaure l'environnement dans tous les cas (try/finally), qu'un
    passage réussisse ou lève. Ne lève jamais — retourne `None` en cas
    d'échec (appelant = hook non-bloquant, cf orchestrator.py).
    """
    overrides = env_overrides if env_overrides is not None else SHADOW_ENV_OVERRIDES
    saved = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    try:
        principle_engine = PrincipleEngine(db_path=db_path, source_type=SOURCE_TYPE_SHADOW)
        principle_engine.evaluate_principles(snapshot_id)

        signal_generator = SignalGenerator(db_path=db_path, source_type=SOURCE_TYPE_SHADOW)
        signal_generator.generate(snapshot_id)

        decision_logger = ShadowDecisionLogger(db_path=db_path, source_type=SOURCE_TYPE_SHADOW)
        return decision_logger.log(snapshot_id)
    except Exception:
        logger.exception("shadow_evaluator: echec passage shadow[%s]", snapshot_id)
        return None
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

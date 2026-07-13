"""order_executor.py — Brief Q5 (volet exécution), 2026-07-13.

Confirmation de périmètre : ce module était explicitement exclu du mandat
Q1-Q5 initial (AGENT.md § « Périmètre GELÉ (ne jamais ouvrir) », doctrine
ROADMAP.md Phase 12). Il a été débloqué par une confirmation directe de
l'utilisateur en session, en réponse à l'annonce explicite que ce module
était le seul point encore bloqué ("active tout ... on dégèle tout ce qui
bloque"). Voir DECISIONS_LOG.md §2026-07-13 pour le détail exact.

`V9_EXECUTION_ENABLED` reste à 0 (OFF) — l'activation reste un geste
séparé et délibéré de l'utilisateur, jamais posé par ce module ni par la
session qui l'a écrit.

DOUBLE VERROU (non contournable, vérifié EN PREMIER, avant toute autre
logique, avant toute tentative de connexion MT4) :
  1. `V9_EXECUTION_ENABLED == "1"` dans l'environnement.
  2. Pour tout ordre > `HITL_LOT_THRESHOLD` lots : confirmation HITL
     explicite (`hitl_reviews.verdict == 'approved'`, la plus récente pour
     ce `decision_id` — table livrée par Brief Q3, jamais `decisions`).
Si l'un des deux manque : échec fermé (fail closed), aucun ordre n'est
construit, aucun fichier n'est écrit, aucune connexion n'est tentée.

Connectivité MT4 : NON VÉRIFIÉE en conditions réelles dans cette session
(machine de dev headless, aucun terminal MT4 démo joignable). La logique
de décision (double verrou, sizing, SL/TP obligatoires) est testée
unitairement de bout en bout avec un pont (bridge) fichier. L'envoi réel
passe par un dépôt de commande JSON dans un répertoire que l'EA MT4 devra
lire — modification EA = action opérateur distincte, hors périmètre de ce
brief (même convention que le multi-paires Brief Q4).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.hitl_reviews_db import get_reviews_for_decision

logger = logging.getLogger("v9.order_executor")

EXECUTION_ENABLED_ENV = "V9_EXECUTION_ENABLED"
HITL_LOT_THRESHOLD = 0.5
VALID_DIRECTIONS = ("haussiere", "baissiere")

ORDER_QUEUE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "order_queue"


class ExecutionDisabledError(Exception):
    """V9_EXECUTION_ENABLED n'est pas à 1 — aucun ordre ne peut partir."""


class HITLConfirmationRequiredError(Exception):
    """Ordre > HITL_LOT_THRESHOLD sans confirmation approuvée dans hitl_reviews."""


class InvalidOrderError(Exception):
    """SL/TP manquant, ou paramètres d'ordre invalides — jamais d'ordre nu."""


def is_execution_enabled() -> bool:
    """Verrou 1. Lecture directe de l'environnement, jamais mise en cache."""
    return os.environ.get(EXECUTION_ENABLED_ENV, "0") == "1"


@dataclass
class OrderRequest:
    decision_id: str
    symbol: str
    direction: str  # "haussiere" / "baissiere" — convention V9 (cf decision_logger)
    lot: float
    sl_pips: float
    tp_pips: float
    entry_price: float | None = None
    magic: int = 90900001
    comment: str = "V9_AUTO"


def _is_hitl_confirmed(decision_id: str, db_path: Path | None = None) -> bool:
    """Verrou 2 (partiel). Dernière review pour ce decision_id, verdict='approved'."""
    reviews = get_reviews_for_decision(decision_id, db_path=db_path)
    if not reviews:
        return False
    return reviews[0]["verdict"] == "approved"


def _validate_order(order: OrderRequest) -> None:
    """Jamais d'ordre nu : SL/TP obligatoires, valeurs sensées."""
    if order.sl_pips is None or order.tp_pips is None:
        raise InvalidOrderError("sl_pips et tp_pips obligatoires — jamais d'ordre nu")
    if order.sl_pips <= 0 or order.tp_pips <= 0:
        raise InvalidOrderError("sl_pips/tp_pips doivent être > 0")
    if order.lot is None or order.lot <= 0:
        raise InvalidOrderError("lot doit être > 0")
    if order.direction not in VALID_DIRECTIONS:
        raise InvalidOrderError(f"direction invalide: {order.direction!r} (attendu {VALID_DIRECTIONS})")
    if not order.decision_id:
        raise InvalidOrderError("decision_id requis (traçabilité + clé HITL)")


def _build_order_command(order: OrderRequest) -> dict[str, Any]:
    """Payload pur, sans I/O — testable indépendamment du bridge MT4."""
    return {
        "command_id": str(uuid.uuid4()),
        "decision_id": order.decision_id,
        "symbol": order.symbol,
        "action": "BUY" if order.direction == "haussiere" else "SELL",
        "lot": round(order.lot, 2),
        "sl_pips": order.sl_pips,
        "tp_pips": order.tp_pips,
        "entry_price": order.entry_price,
        "magic": order.magic,
        "comment": order.comment,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }


def _send_via_bridge(payload: dict[str, Any], queue_dir: Path | None = None) -> dict[str, Any]:
    """Dépose la commande en JSON dans le répertoire lu par l'EA MT4.

    Aucune connectivité MT4 réelle n'est établie ici — écriture fichier
    uniquement. La lecture/exécution côté EA MT4 est une action opérateur
    distincte, hors périmètre de ce brief.
    """
    queue_dir = queue_dir or ORDER_QUEUE_DIR
    queue_dir.mkdir(parents=True, exist_ok=True)
    file_path = queue_dir / f"{payload['command_id']}.json"
    file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "sent": True,
        "reason": "queued",
        "command_id": payload["command_id"],
        "file": str(file_path),
    }


def send_order(
    order: OrderRequest,
    *,
    db_path: Path | None = None,
    queue_dir: Path | None = None,
) -> dict[str, Any]:
    """Point d'entrée unique pour émettre un ordre réel.

    DOUBLE VERROU vérifié EN PREMIER, avant toute autre logique :
      1. `is_execution_enabled()` — sinon retour immédiat, rien d'autre ne
         s'exécute (pas de lecture HITL, pas de validation, pas de fichier).
      2. Pour lot > HITL_LOT_THRESHOLD : `_is_hitl_confirmed()`.

    Ne lève JAMAIS d'exception pour les deux verrous — retourne
    `{"sent": False, "reason": ...}` (fail closed silencieux, cohérent
    avec le pipeline live qui ne doit jamais crasher sur un refus attendu).
    Lève InvalidOrderError si l'ordre est structurellement invalide
    (SL/TP manquant, lot négatif, etc.) — ça, c'est un bug appelant, pas un
    refus normal.
    """
    # Verrou 1 — EN PREMIER. Rien d'autre ne s'exécute si absent.
    if not is_execution_enabled():
        logger.info(
            "order_executor.blocked: V9_EXECUTION_ENABLED != 1 (decision_id=%s)",
            getattr(order, "decision_id", None),
        )
        return {"sent": False, "reason": "execution_disabled"}

    # Verrou 2 — HITL pour tout ordre > seuil.
    if order.lot is not None and order.lot > HITL_LOT_THRESHOLD:
        if not _is_hitl_confirmed(order.decision_id, db_path=db_path):
            logger.info(
                "order_executor.blocked: hitl_required (decision_id=%s, lot=%.2f)",
                order.decision_id, order.lot,
            )
            return {"sent": False, "reason": "hitl_required"}

    _validate_order(order)

    payload = _build_order_command(order)
    result = _send_via_bridge(payload, queue_dir=queue_dir)
    logger.warning(
        "order_executor.SENT: decision_id=%s symbol=%s action=%s lot=%.2f sl=%.1f tp=%.1f",
        order.decision_id, order.symbol, payload["action"], order.lot, order.sl_pips, order.tp_pips,
    )
    return result


def build_order_from_paper_risk(
    decision_id: str,
    symbol: str,
    direction: str,
    risk_eval: dict[str, Any],
) -> OrderRequest:
    """Construit une OrderRequest depuis la sortie de PaperRiskManager.evaluate().

    Ne réimplémente pas le sizing — lit position_size/sl_pips/tp_pips déjà
    calculés par `core/v9/paper_risk_manager.py`.
    """
    if not risk_eval.get("go"):
        raise InvalidOrderError(
            f"risk_eval.go=False ({risk_eval.get('raison_blocage')}) — pas d'ordre à construire"
        )
    return OrderRequest(
        decision_id=decision_id,
        symbol=symbol,
        direction=direction,
        lot=risk_eval["position_size"],
        sl_pips=risk_eval["sl_pips"],
        tp_pips=risk_eval["tp_pips"],
    )

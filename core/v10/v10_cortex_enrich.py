"""V10 Cortex Enrichment — branche les modules orphelins dans le Cortex (Phase 8, Cognitive Continuum).

Complète la lecture riche du Cortex en absorbant les 3 modules qui étaient
orphelins (importés seulement par `__init__.py`) :
  - `v10_delta_flow`    : flux de delta (imbalance, absorption, stacked imbalance)
  - `v10_liquidity_map` : carte de liquidité (equal highs/lows, order blocks, FVG, swing)
  - `v10_grammar_v9_final` : concepts de grammaire V9 restants (CONTEXTE, CROISEMENT,
    CROISEMENT_CONFIRMATION, GRAVITY_RESPRING, POWER_ANGLE_BREAK, RAW_NODE_BIRTH, SIGNAL_OPEN)

`enrich_interp()` enrichit une interprétation du Cortex avec ces 3 lectures.
Résout l'auto-cohérence : plus aucun module de lecture n'est laissé de côté.

R2 additif pur (0 import core/v9/). R6 fail-open. R9 traçable. R10 compute only.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

log = logging.getLogger(__name__)


def enrich_interp(
    interp: Dict,
    *,
    symbol: str,
    timeframe: str,
    bars: list,
    timestamp: str = "",
) -> Dict:
    """Enrichit une interprétation du Cortex avec delta_flow + liquidity_map + grammar.

    R6 fail-open : module échoue → section absente/None, jamais de crash.
    R9 : chaque section tracée dans interp['audit']['steps'].
    """
    audit_steps = interp.get("audit", {}).get("steps", []) or []

    # 1. Delta flow (flux de volume)
    try:
        from core.v10.v10_delta_flow import compute_delta
        delta = compute_delta(symbol, timeframe, bars, timestamp=timestamp)
        interp["delta_flow"] = {
            "imbalance_ratio": round(getattr(delta, "imbalance_ratio", 0.0), 4),
            "direction_delta": str(getattr(delta, "direction_delta", "UNKNOWN")),
            "absorption_detected": bool(getattr(delta, "absorption_detected", False)),
            "stacked_imbalance": bool(getattr(delta, "stacked_imbalance", False)),
        }
        audit_steps.append("delta_flow")
    except Exception as exc:
        log.warning("delta_flow échoué (R6): %s", exc)
        audit_steps.append("delta_flow_error")

    # 2. Liquidity map (zones de liquidité)
    try:
        from core.v10.v10_liquidity_map import get_liquidity_map
        current_price = bars[-1]["close"] if bars else None
        lq = get_liquidity_map(symbol, timeframe, bars, timestamp=timestamp,
                               current_price=current_price)
        interp["liquidity"] = {
            "n_zones": getattr(lq, "n_zones_detected", 0),
            "price_in_zone": bool(getattr(lq, "price_in_zone", False)),
            "nearest_buy": getattr(getattr(lq, "nearest_buy_zone", None), "zone_type", None),
            "nearest_sell": getattr(getattr(lq, "nearest_sell_zone", None), "zone_type", None),
        }
        audit_steps.append("liquidity_map")
    except Exception as exc:
        log.warning("liquidity_map échoué (R6): %s", exc)
        audit_steps.append("liquidity_map_error")

    # 3. Grammar V9 final (concepts restants)
    try:
        from core.v10.v10_grammar_v9_final import evaluate_grammar_v9_final
        grammar = evaluate_grammar_v9_final(marche_ouvert=True, session_marche=True)
        interp["grammar_final"] = {
            "n_detected": grammar.get("n_detected", 0),
            "best": grammar.get("best"),
        }
        audit_steps.append("grammar_v9_final")
    except Exception as exc:
        log.warning("grammar_v9_final échoué (R6): %s", exc)
        audit_steps.append("grammar_v9_final_error")

    interp["audit"] = dict(interp.get("audit", {}))
    interp["audit"]["steps"] = audit_steps
    return interp


__all__ = ["enrich_interp"]

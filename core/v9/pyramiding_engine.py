"""PyramidingEngine — Scaling de position sur confluence (Phase 13.2).

Détecte les conditions de pyramiding (ajout de position) quand :
  - Plusieurs principes alignés dans la même direction
  - Confluence multi-TF confirmée
  - Zone_type favorable (naissance, 2e_jambe)
  - Régime directionnel (CASSURE, EXTENSION)

Usage :
    engine = PyramidingEngine()
    signal = engine.evaluate(arbiter_result, context)
    # → {"pyramiding_allowed": bool, "multiplier": float, "reason": str}
"""
from __future__ import annotations

from typing import Any

PYRAMIDING_VERSION = "1.0"
PYRAMIDING_VERSION_V2 = "2.0"  # ajouté Phase 12 FTMO pour STARS/SUPER_STARS


class PyramidingEngine:
    """Évalue si un trade peut être renforcé (pyramiding).

    Règles de décision :
      1. Confluence principes : ≥ 3 principes alignés → bonus
      2. Confluence MTF : emboitement M5+M15+H1 → bonus
      3. Zone_type : naissance ou 2e_jambe → favorable
      4. Régime : CASSURE ou EXTENSION → favorable
      5. News : NEWS_SHOCK → interdit

    Multiplicateurs :
      - Base : 1.0 (position standard)
      - 3+ principes : +0.3
      - Confluence MTF : +0.3
      - Zone naissance/2e_jambe : +0.2
      - Régime directionnel : +0.2
      - Max : 2.0 (plafond)
    """
    def __init__(
        self,
        *,
        min_principes_pyramiding: int = 3,
        max_multiplier: float = 2.0,
        base_multiplier: float = 1.0,
    ) -> None:
        self.min_principes_pyramiding = min_principes_pyramiding
        self.max_multiplier = max_multiplier
        self.base_multiplier = base_multiplier

    def evaluate(
        self,
        arbiter_result: dict,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Évalue le potentiel de pyramiding.

        Args:
            arbiter_result: Sortie de Arbiter.consolidate()
            context: Shared context (zone_type, regime, news, etc.)

        Returns:
            dict avec pyramiding_allowed, multiplier, reasons
        """
        context = context or {}
        multiplier = self.base_multiplier
        reasons: list[str] = []

        # Vérifications bloquantes
        if context.get("news_phase") == "NEWS_SHOCK":
            return {
                "pyramiding_allowed": False,
                "multiplier": 1.0,
                "reason": "news_shock_block",
                "reasons": ["NEWS_SHOCK → pyramiding interdit"],
                "pyramiding_version": PYRAMIDING_VERSION,
            }

        nb_principes = arbiter_result.get("nb_principes_actifs", 0)
        if nb_principes < self.min_principes_pyramiding:
            return {
                "pyramiding_allowed": False,
                "multiplier": 1.0,
                "reason": "insufficient_principes",
                "reasons": [f"principes ({nb_principes}) < min ({self.min_principes_pyramiding})"],
                "pyramiding_version": PYRAMIDING_VERSION,
            }

        # 1. Confluence principes
        if nb_principes >= 3:
            multiplier += 0.3
            reasons.append(f"confluence {nb_principes} principes (+0.3)")

        # 2. Confluence MTF
        mtf_score = context.get("coalition_mtf_score", 0) or 0
        if mtf_score >= 2:
            multiplier += 0.3
            reasons.append(f"confluence MTF score={mtf_score} (+0.3)")

        # 3. Zone_type favorable
        zone_type = context.get("zone_type", "")
        if zone_type in ("naissance", "2e_jambe"):
            multiplier += 0.2
            reasons.append(f"zone_type={zone_type} (+0.2)")

        # 4. Régime directionnel
        regime = context.get("regime_type", "")
        if regime in ("CASSURE", "EXTENSION"):
            multiplier += 0.2
            reasons.append(f"régime={regime} (+0.2)")

        # Plafond
        multiplier = min(multiplier, self.max_multiplier)

        pyramiding_allowed = multiplier > self.base_multiplier

        return {
            "pyramiding_allowed": pyramiding_allowed,
            "multiplier": round(multiplier, 2),
            "reason": "ok" if pyramiding_allowed else "base_only",
            "reasons": reasons,
            "nb_principes": nb_principes,
            "mtf_score": mtf_score,
            "zone_type": zone_type,
            "regime_type": regime,
            "pyramiding_version": PYRAMIDING_VERSION,
        }

"""v9_pyramiding_engine.py — PyramidingEngine V2 avec boost STARS / SUPER_STARS.

Wrapper V2 (Phase 12+ FTMO) qui hérite de PyramidingEngine (Phase 13.2) et ajoute :
  - BOOST_STARS : multiplicateur ×1.3 quand 3+ principes confluents + MTF confirmé
  - BOOST_SUPER_STARS : multiplicateur ×1.5 quand 4+ principes + confluence MTF + zone naissance
  - Plafond FTMO : 2.0 max (déjà codé dur dans PyramidingEngine V1)
  - Kill switches V9_PYRAMIDING_BOOST_STARS / V9_PYRAMIDING_BOOST_SUPER_STARS

R2 additif — hérite de PyramidingEngine V1, ne modifie pas son interface.
R6 fail-open — défauts OFF, pas d'impact si switch désactivé.
R14 git = vérité — pas d'invention, le moteur V1 sert de référence.
R23 — consommateurs YAML inchangés (le boost est appliqué au multiplicateur final).

Auteur : Hermés, Phase 12 FTMO 03/08/2026 (motion CEO « go max plein pouvoir »).
"""
from __future__ import annotations

import os
from typing import Any

from core.v9.pyramiding_engine import PyramidingEngine, PYRAMIDING_VERSION_V2

# === Kill switches (R25' strict) ===
PYRAMIDING_BOOST_STARS_ENV = "V9_PYRAMIDING_BOOST_STARS"
PYRAMIDING_BOOST_SUPER_STARS_ENV = "V9_PYRAMIDING_BOOST_SUPER_STARS"

# Multiplicateurs FTMO (sortie des clous DD cap, motion CEO Phase 12)
BOOST_STARS_MULTIPLIER = 1.3       # +30% quand 3-4 principes confluents + MTF
BOOST_SUPER_STARS_MULTIPLIER = 1.5  # +50% quand 4+ principes + MTF + zone naissance

# Plafond FTMO (cohérent avec PyramidingEngine.max_multiplier)
BOOST_MAX_FINAL = 2.0


def _env_on(name: str, default: str = "0") -> bool:
    """Lecture env défensive (R6 fail-open)."""
    return os.environ.get(name, default).strip() in ("1", "true", "TRUE", "yes", "YES")


class PyramidingEngineV2(PyramidingEngine):
    """PyramidingEngine V2 — ajoute les boosts STARS / SUPER_STARS.

    R2 additif sur PyramidingEngine V1 (Phase 13.2). Le multiplicateur de V1
    est composé multiplicativement avec le boost STARS :
        final = min(v1_multiplier * boost, BOOST_MAX_FINAL)

    R6 fail-open : si env non armé, comportement = V1 strictement identique.
    """

    def __init__(
        self,
        *,
        min_principes_pyramiding: int = 3,
        max_multiplier: float = BOOST_MAX_FINAL,
        base_multiplier: float = 1.0,
    ) -> None:
        super().__init__(
            min_principes_pyramiding=min_principes_pyramiding,
            max_multiplier=max_multiplier,
            base_multiplier=base_multiplier,
        )
        self.boost_stars_enabled = _env_on(PYRAMIDING_BOOST_STARS_ENV)
        self.boost_super_stars_enabled = _env_on(PYRAMIDING_BOOST_SUPER_STARS_ENV)

    def evaluate(
        self,
        arbiter_result: dict,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Évalue pyramiding V1 puis applique boost STARS / SUPER_STARS si armés.

        Returns:
            dict avec pyramiding_allowed, multiplier, reasons, stars_level.
        """
        result = super().evaluate(arbiter_result, context)
        multiplier_v1 = result.get("multiplier", 1.0)
        stars_level = "base"

        if not result.get("pyramiding_allowed", False):
            # Pas de pyramiding de base — on n'applique aucun boost
            return {
                **result,
                "stars_level": stars_level,
                "boost_applied": 1.0,
                "pyramiding_version": PYRAMIDING_VERSION_V2,
            }

        nb_principes = arbiter_result.get("nb_principes_actifs", 0)
        mtf_score = (context or {}).get("coalition_mtf_score", 0) or 0
        zone_type = (context or {}).get("zone_type", "")
        regime = (context or {}).get("regime_type", "")

        boost = 1.0
        reasons_extra: list[str] = []
        applied_level = "base"

        # SUPER_STARS : 4+ principes + MTF confirmé + zone naissance/2e_jambe
        if (
            self.boost_super_stars_enabled
            and nb_principes >= 4
            and mtf_score >= 2
            and zone_type in ("naissance", "2e_jambe")
        ):
            boost = BOOST_SUPER_STARS_MULTIPLIER
            applied_level = "super_stars"
            reasons_extra.append(
                f"SUPER_STARS: {nb_principes}p + MTF={mtf_score} + zone={zone_type} (x{boost})"
            )
        # STARS : 3+ principes + MTF confirmé
        elif self.boost_stars_enabled and nb_principes >= 3 and mtf_score >= 1:
            boost = BOOST_STARS_MULTIPLIER
            applied_level = "stars"
            reasons_extra.append(
                f"STARS: {nb_principes}p + MTF={mtf_score} (x{boost})"
            )

        final_multiplier = min(multiplier_v1 * boost, self.max_multiplier)
        boosted = final_multiplier > multiplier_v1

        return {
            **result,
            "multiplier": round(final_multiplier, 2),
            "multiplier_v1": multiplier_v1,
            "boost_applied": round(boost, 2) if boosted else 1.0,
            "stars_level": applied_level if boosted else result.get("stars_level", "base"),
            "reasons": result.get("reasons", []) + reasons_extra,
            "pyramiding_version": PYRAMIDING_VERSION_V2,
        }


def pyramiding_boost_stars_enabled() -> bool:
    """Accessor pour kill switch (R25')."""
    return _env_on(PYRAMIDING_BOOST_STARS_ENV)


def pyramiding_boost_super_stars_enabled() -> bool:
    """Accessor pour kill switch (R25')."""
    return _env_on(PYRAMIDING_BOOST_SUPER_STARS_ENV)

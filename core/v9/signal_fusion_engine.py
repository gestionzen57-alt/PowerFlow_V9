"""SignalFusionEngine — fusion de principes faibles en signal fort.

Chantier B DIVERSIFY (2026-07-16, Claude Opus). PowerFlow V9.

Problème : plusieurs principes secondaires se déclenchent avec une confiance
individuelle modérée (< seuil de trade) et ne produisent donc jamais de signal
exploitable, alors que leur ACCORD collectif sur une même direction est un
signal plus fiable qu'un seul principe fort isolé.

Ce module est **pur** (R18 — zéro LLM, zéro I/O, zéro DB) : il prend une liste
de principes déclenchés (direction + confiance) et retourne un signal fusionné
ou None. Le SignalGenerator l'utilise en **hook additif** (R2) : la fusion ne
peut QUE relever la confiance d'un signal déjà directionnel ; elle ne retourne
jamais la direction et n'abaisse jamais la confiance.

Règles de fusion (spec CEO Søn) :
- 1 principe confiance ≥ 80 + ≥ 1 autre confiance ≥ 50 → confiance = plus fort + 10 (boost)
- 3 principes même direction, confiance ≥ 40 chacun → confiance = 70
- 2 principes même direction, confiance ≥ 50 chacun → confiance = 65
- directions opposées présentes → conflit → None (pas de signal)
- aucune règle applicable → None (comportement SignalGenerator inchangé)

Précédence : boost > triple_40 > double_50 (la règle la plus forte l'emporte).
"""

from __future__ import annotations

from typing import Any

DIRECTIONNELLES = ("haussiere", "baissiere")


class SignalFusionEngine:
    """Fusionne des principes faibles concordants en un signal renforcé.

    Les seuils sont paramétrables (défauts = spec CEO) pour permettre une
    calibration future sans réécrire la logique.
    """

    def __init__(
        self,
        *,
        boost_high: float = 80.0,
        boost_partner: float = 50.0,
        boost_increment: float = 10.0,
        triple_min_conf: float = 40.0,
        triple_confidence: float = 70.0,
        double_min_conf: float = 50.0,
        double_confidence: float = 65.0,
    ) -> None:
        self.boost_high = boost_high
        self.boost_partner = boost_partner
        self.boost_increment = boost_increment
        self.triple_min_conf = triple_min_conf
        self.triple_confidence = triple_confidence
        self.double_min_conf = double_min_conf
        self.double_confidence = double_confidence

    def fuse(self, triggered_principles: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Combine plusieurs principes faibles en un signal fort.

        Args:
            triggered_principles : liste de dicts avec au minimum les clés
                ``direction`` (``"haussiere"``/``"baissiere"``/``"neutre"``/None)
                et ``confidence`` (numérique). ``principle_id`` est optionnel
                (repris dans la traçabilité du signal fusionné).

        Returns:
            dict {direction, confidence, fusion_rule, n_fused, principle_ids}
            si une règle de fusion s'applique, sinon None.
        """
        # Ne garder que les principes directionnels à confiance numérique.
        directional = [
            p for p in triggered_principles
            if p.get("direction") in DIRECTIONNELLES
            and isinstance(p.get("confidence"), (int, float))
        ]
        if len(directional) < 2:
            return None  # pas de fusion possible avec moins de 2 votes

        hauss = [p for p in directional if p["direction"] == "haussiere"]
        baiss = [p for p in directional if p["direction"] == "baissiere"]

        # Conflit : des principes votent des directions opposées → annulation.
        if hauss and baiss:
            return None

        same = hauss or baiss
        direction = same[0]["direction"]
        confs = sorted((float(p["confidence"]) for p in same), reverse=True)
        strongest = confs[0]
        n_ge_high = sum(1 for c in confs if c >= self.boost_high)
        n_ge_partner = sum(1 for c in confs if c >= self.boost_partner)
        n_ge_triple = sum(1 for c in confs if c >= self.triple_min_conf)
        n_ge_double = sum(1 for c in confs if c >= self.double_min_conf)

        # Précédence : boost (le plus fort) > triple_40 > double_50.
        # boost : 1 principe ≥ boost_high ET ≥ 1 AUTRE ≥ boost_partner
        # (le ≥ boost_high compte déjà dans ≥ boost_partner → il en faut ≥ 2).
        if n_ge_high >= 1 and n_ge_partner >= 2:
            fused_conf = min(100.0, strongest + self.boost_increment)
            rule = "boost_high_plus_partner"
        elif n_ge_triple >= 3:
            fused_conf = self.triple_confidence
            rule = "triple_min_conf"
        elif n_ge_double >= 2:
            fused_conf = self.double_confidence
            rule = "double_min_conf"
        else:
            return None

        return {
            "direction": direction,
            "confidence": round(fused_conf),
            "fusion_rule": rule,
            "n_fused": len(same),
            "principle_ids": [p.get("principle_id") for p in same],
        }

"""PhaseClassifier — règles pures signaux → phase de cycle (Phase 13.3).

Ce module contient la logique de décision qui, à partir d'un `CycleSignals`
normalisé (produit par `MarketCycleDetector.extract`), attribue une
`MarketPhase` et une confiance. Il est volontairement séparé du détecteur :
le détecteur EXTRAIT (I/O contexte), le classifieur DÉCIDE (règles pures,
sans dépendance externe → testable en isolation).

Priorité des règles (une phase l'emporte dès qu'elle matche) :

  1. CLIMAX        — vélocité extrême / épuisement violent.
  2. CASSURE       — breakout confirmé (régime CASSURE, point de rupture,
                     initiation + extension + accélération).
  3. TREND         — mouvement directionnel soutenu (régime EXTENSION,
                     développement + coalition montante/stable).
  4. DISTRIBUTION  — épuisement sans vélocité extrême (culmination,
                     coalition déclinante, décélération, REJET).
  5. RETOUR        — mean reversion (RETOUR_EQUILIBRE, resolution, MRZ).
  6. ACCUMULATION  — range / compression (PALIER, initiation calme). Défaut
                     tradable quand des signaux existent mais rien d'actif.

Si aucun signal exploitable (`signal_richness == 0`) → INDETERMINE
(le DynamicRiskManager retombera alors sur le fallback statique).

Doctrine R18 : code pur, aucun LLM. R6 : ne lève jamais.
"""
from __future__ import annotations

from core.v9.market_cycle_detector import (
    CLIMAX_VELOCITY,
    CycleSignals,
    MarketPhase,
)

PHASE_CLASSIFIER_VERSION = "1.0"


class PhaseClassifier:
    """Attribue une `MarketPhase` + confiance à un `CycleSignals`."""

    def classify(
        self, signals: CycleSignals
    ) -> tuple[MarketPhase, float, list[str]]:
        """Retourne (phase, confidence ∈ [0,1], rationale).

        Déterministe, sans effet de bord, ne lève jamais.
        """
        if signals is None or signals.signal_richness == 0:
            return MarketPhase.INDETERMINE, 0.0, ["aucun signal exploitable"]

        # 1. CLIMAX — vélocité extrême. Épuisement violent, priorité absolue :
        #    on ne prend pas de nouvelle position, on protège l'existant.
        if signals.velocity_abs >= CLIMAX_VELOCITY:
            conf = _clip(0.6 + min(signals.velocity_abs - CLIMAX_VELOCITY, 1.0) * 0.3)
            return MarketPhase.CLIMAX, conf, [
                f"vélocité extrême ({signals.velocity_abs:.2f} ≥ {CLIMAX_VELOCITY})",
            ]
        # Culmination + accélération franche = climax comportemental même si la
        # vélocité brute n'est pas dans la queue extrême.
        if (
            signals.behavior_phase == "culmination"
            and signals.acceleration == "acceleration"
            and signals.compression == "extension"
        ):
            return MarketPhase.CLIMAX, 0.6, [
                "culmination + accélération + extension (climax comportemental)",
            ]

        # 2. CASSURE — breakout. Le stop doit être large (le pullback ne doit
        #    pas nous éjecter), le TP ambitieux.
        reasons: list[str] = []
        if signals.regime_type == "CASSURE":
            reasons.append("régime CASSURE")
        if signals.point_de_rupture:
            reasons.append("point de rupture détecté")
        if (
            signals.behavior_phase == "initiation"
            and signals.compression == "extension"
            and signals.acceleration == "acceleration"
        ):
            reasons.append("initiation + extension + accélération")
        if reasons:
            conf = _clip(0.55 + 0.15 * len(reasons))
            return MarketPhase.CASSURE, conf, reasons

        # 3. TREND — mouvement directionnel soutenu. Trailing + break-even
        #    rapide pour laisser courir tout en sécurisant.
        trend_reasons: list[str] = []
        if signals.regime_type == "EXTENSION":
            trend_reasons.append("régime EXTENSION")
        if (
            signals.behavior_phase == "developpement"
            and signals.coalition_trend in ("montante", "stable")
            and signals.acceleration != "deceleration"
        ):
            trend_reasons.append("développement + coalition soutenue")
        if (
            signals.coalition_class == "forte"
            and signals.coalition_trend == "montante"
            and signals.acceleration == "acceleration"
        ):
            trend_reasons.append("coalition forte montante + accélération")
        if trend_reasons:
            conf = _clip(0.5 + 0.15 * len(trend_reasons)
                         + (0.1 if signals.mtf_emboitement else 0.0))
            return MarketPhase.TREND, conf, trend_reasons

        # 4. DISTRIBUTION — épuisement / divergence. On prend le profit vite.
        dist_reasons: list[str] = []
        if signals.regime_type == "REJET":
            dist_reasons.append("régime REJET")
        if signals.behavior_phase == "culmination":
            dist_reasons.append("phase culmination")
        if signals.coalition_trend == "declinante" and signals.coalition_age >= 2:
            dist_reasons.append("coalition déclinante et âgée")
        if signals.compression == "extension" and signals.acceleration == "deceleration":
            dist_reasons.append("extension en décélération (divergence)")
        if dist_reasons:
            conf = _clip(0.5 + 0.15 * len(dist_reasons))
            return MarketPhase.DISTRIBUTION, conf, dist_reasons

        # 5. RETOUR — mean reversion. Objectif modeste, SL large.
        retour_reasons: list[str] = []
        if signals.regime_type == "RETOUR_EQUILIBRE":
            retour_reasons.append("régime RETOUR_EQUILIBRE")
        if signals.mean_reversion_zone:
            retour_reasons.append("zone de mean-reversion")
        if signals.behavior_phase == "resolution":
            retour_reasons.append("phase resolution")
        if retour_reasons:
            conf = _clip(0.5 + 0.15 * len(retour_reasons))
            return MarketPhase.RETOUR, conf, retour_reasons

        # 6. ACCUMULATION — range / compression. Défaut tradable : coalitions
        #    en formation, volatilité faible, objectif modeste, SL serré.
        acc_reasons: list[str] = []
        if signals.regime_type == "PALIER":
            acc_reasons.append("régime PALIER")
        if signals.compression == "compression":
            acc_reasons.append("compression")
        if signals.behavior_phase == "initiation":
            acc_reasons.append("phase initiation")
        if signals.coalition_age <= 2 and signals.coalition_trend != "declinante":
            acc_reasons.append("coalition naissante")
        if not acc_reasons:
            acc_reasons.append("marché neutre (range par défaut)")
        conf = _clip(0.4 + 0.12 * len(acc_reasons))
        return MarketPhase.ACCUMULATION, conf, acc_reasons


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, round(x, 3)))

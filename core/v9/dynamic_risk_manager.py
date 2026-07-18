"""DynamicRiskManager — SL/TP/break-even/trailing adaptatifs (Phase 13.3).

Le système lit désormais le marché en haute définition (5 paires, 8 devises,
coalitions HTF lissées, confirmation LTF, cycles et phases). La gestion du
risque, elle, était restée statique : TP=8/SL=15, identiques pour toutes les
paires, tous les régimes, toutes les sessions — un héritage de l'époque
aveugle.

Ce module adapte la gestion du risque à ce que le système sait maintenant
lire :

  cycle/phase (MarketCycleDetector) → profil SL/TP de base
                                     → modulation coalition HTF/LTF + force
                                     → garde-fou session (politique O4)
                                     → RiskDecision (SL/TP/exit/trailing/BE)

Un breakout en début de Londres n'a pas le même stop qu'un climax en fin de
New York ; une coalition HTF (D1/H4) a une espérance de vie plus longue qu'une
coalition LTF (M5/M15) éphémère. Le RiskManager le reflète.

STATUT : SHADOW par défaut. Le module ÉVALUE et DÉCRIT ; il n'APPLIQUE rien.
Le câblage dans `trade_engine` attache le résultat au diagnostic sans modifier
le SL/TP réellement utilisé. L'activation (mode APPLY) est une décision CEO
(Søn), pas un défaut de code.

Doctrine :
  - R18 : code pur, aucun LLM.
  - R2  : additif — le RiskManager statique reste le fallback.
  - R6  : try/except, ne bloque jamais ; phase indéterminée / erreur → fallback.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.v9.exit_simulator import (
    DYNAMIC_DEFAULT,
    DYNAMIC_PROFILES,
    is_session_tradable,
)
from core.v9.market_cycle_detector import (
    MarketCycleDetector,
    MarketPhase,
)

log = logging.getLogger(__name__)

DYNAMIC_RISK_VERSION = "1.0"

# ── Profils SL/TP par phase de cycle ──────────────────────────────────
# Chaque profil : SL/TP de base (pips), stratégie de sortie, activation du
# trailing (fraction du TP à partir de laquelle il s'arme, None = jamais),
# distance du trailing (fraction du SL), break-even (fraction du TP à partir
# de laquelle on remonte le stop à l'entrée, None = jamais), et si la phase
# autorise l'ouverture d'une NOUVELLE position.
#
# Rationale par phase :
#   ACCUMULATION : range, volatilité faible        → SL serré, TP modeste.
#   CASSURE      : breakout, peut pullback          → SL large, TP ambitieux, trailing.
#   TREND        : directionnel, coalitions solides → trailing serré, BE rapide.
#   DISTRIBUTION : épuisement, divergence           → prendre le profit vite, BE.
#   CLIMAX       : extrême, vélocité max            → aucune nouvelle position.
#   RETOUR       : mean reversion                   → objectif modeste, SL large.
PHASE_PROFILES: dict[MarketPhase, dict[str, Any]] = {
    MarketPhase.ACCUMULATION: {
        "sl_pips": 10.0, "tp_pips": 8.0, "exit_strategy": "TP_SL",
        "trailing_activation": None, "trailing_distance_ratio": None,
        "break_even_at": None, "allow_new_position": True,
    },
    MarketPhase.CASSURE: {
        "sl_pips": 18.0, "tp_pips": 22.0, "exit_strategy": "TRAILING",
        "trailing_activation": 0.5, "trailing_distance_ratio": 0.5,
        "break_even_at": 0.3, "allow_new_position": True,
    },
    MarketPhase.TREND: {
        "sl_pips": 14.0, "tp_pips": 26.0, "exit_strategy": "TRAILING",
        "trailing_activation": 0.25, "trailing_distance_ratio": 0.5,
        "break_even_at": 0.2, "allow_new_position": True,
    },
    MarketPhase.DISTRIBUTION: {
        "sl_pips": 10.0, "tp_pips": 10.0, "exit_strategy": "TP_SL",
        "trailing_activation": None, "trailing_distance_ratio": None,
        "break_even_at": 0.5, "allow_new_position": True,
    },
    MarketPhase.CLIMAX: {
        "sl_pips": 8.0, "tp_pips": 8.0, "exit_strategy": "TIME_BASED",
        "trailing_activation": None, "trailing_distance_ratio": None,
        "break_even_at": None, "allow_new_position": False,
    },
    MarketPhase.RETOUR: {
        "sl_pips": 12.0, "tp_pips": 8.0, "exit_strategy": "TP_SL",
        "trailing_activation": None, "trailing_distance_ratio": None,
        "break_even_at": None, "allow_new_position": True,
    },
}

# ── Bornes de sécurité (clamp final) ──────────────────────────────────
SL_MIN, SL_MAX = 6.0, 25.0
TP_MIN, TP_MAX = 4.0, 40.0

# ── Multiplicateurs de modulation coalition ───────────────────────────
# Une coalition HTF (D1/H4) porte un mouvement plus ample et durable →
# TP/SL élargis. Une coalition LTF (M5/M15) est éphémère → resserrés.
MOD_HTF_TP, MOD_HTF_SL = 1.5, 1.2
MOD_LTF_TP, MOD_LTF_SL = 0.8, 0.8
MOD_MTF_ALIGNED_TP = 1.3       # emboîtement multi-TF (confluence = confirmation)
MOD_COALITION_STRONG_TP = 1.2  # coalition intensité forte (>60)
MOD_COALITION_WEAK_TP = 0.7    # coalition intensité faible (<30)


@dataclass
class RiskDecision:
    """Décision de gestion de risque adaptative (descriptive en SHADOW)."""
    tp_pips: float
    sl_pips: float
    exit_strategy: str
    allow_new_position: bool = True
    trailing_activation: float | None = None   # fraction du TP
    trailing_distance: float | None = None     # pips
    break_even_at: float | None = None         # fraction du TP
    rr_ratio: float = 0.0
    phase: str = MarketPhase.INDETERMINE.value
    phase_confidence: float = 0.0
    coalition_class: str | None = None
    mtf_depth: str | None = None
    session: str | None = None
    session_tradable: bool = True
    modulation: dict[str, float] = field(default_factory=dict)
    source: str = "dynamic"                    # "dynamic" | "fallback"
    rationale: list[str] = field(default_factory=list)
    dynamic_risk_version: str = DYNAMIC_RISK_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp_pips": self.tp_pips,
            "sl_pips": self.sl_pips,
            "rr_ratio": self.rr_ratio,
            "exit_strategy": self.exit_strategy,
            "allow_new_position": self.allow_new_position,
            "trailing_activation": self.trailing_activation,
            "trailing_distance": self.trailing_distance,
            "break_even_at": self.break_even_at,
            "phase": self.phase,
            "phase_confidence": self.phase_confidence,
            "coalition_class": self.coalition_class,
            "mtf_depth": self.mtf_depth,
            "session": self.session,
            "session_tradable": self.session_tradable,
            "modulation": dict(self.modulation),
            "source": self.source,
            "rationale": list(self.rationale),
            "dynamic_risk_version": self.dynamic_risk_version,
        }


class SLTPCalibrator:
    """Calcule SL/TP/exit à partir de la phase, de la coalition et de la
    session. Logique pure (aucune I/O), testable en isolation."""

    def compute(
        self, cycle_state, session: str | None = None, global_regime: Any = None,
    ) -> RiskDecision:
        """Calibre une `RiskDecision` depuis un `CycleState`.

        Args:
            cycle_state : sortie de MarketCycleDetector.detect().
            session     : session marché (asie/london/...). Si None, tirée
                          des signaux du cycle.
            global_regime : GlobalRegime optionnel (P3 quantique risk-on/off).
                          Si fourni, module le TP via `tp_modulation` (risk-off
                          tempère, risk-on assume). Défaut None → aucun effet
                          (R2 : rétro-compatible).
        """
        signals = cycle_state.signals
        phase = cycle_state.phase
        session = session or signals.session

        profile = PHASE_PROFILES.get(phase)
        if profile is None:
            # INDETERMINE (ou phase inconnue) : pas de calibration dynamique.
            return self._fallback_decision(session=session, phase=phase)

        sl = float(profile["sl_pips"])
        tp = float(profile["tp_pips"])
        modulation: dict[str, float] = {}
        rationale = list(cycle_state.rationale)

        # ── Modulation coalition : profondeur MTF ──
        if signals.is_htf:
            tp *= MOD_HTF_TP
            sl *= MOD_HTF_SL
            modulation["htf_tp"] = MOD_HTF_TP
            modulation["htf_sl"] = MOD_HTF_SL
            rationale.append(f"coalition HTF ({signals.mtf_depth}) → TP×{MOD_HTF_TP}")
        elif signals.is_ltf:
            tp *= MOD_LTF_TP
            sl *= MOD_LTF_SL
            modulation["ltf_tp"] = MOD_LTF_TP
            modulation["ltf_sl"] = MOD_LTF_SL
            rationale.append(f"coalition LTF ({signals.mtf_depth}) → TP×{MOD_LTF_TP}")

        # ── Modulation coalition : emboîtement multi-TF (confluence) ──
        if signals.mtf_emboitement:
            tp *= MOD_MTF_ALIGNED_TP
            modulation["mtf_aligned_tp"] = MOD_MTF_ALIGNED_TP
            rationale.append(f"emboîtement multi-TF → TP×{MOD_MTF_ALIGNED_TP}")

        # ── Modulation coalition : intensité (force de conviction) ──
        coalition_class = signals.coalition_class
        if coalition_class == "forte":
            tp *= MOD_COALITION_STRONG_TP
            modulation["coalition_strong_tp"] = MOD_COALITION_STRONG_TP
            rationale.append(f"coalition forte → TP×{MOD_COALITION_STRONG_TP}")
        elif coalition_class == "faible":
            tp *= MOD_COALITION_WEAK_TP
            modulation["coalition_weak_tp"] = MOD_COALITION_WEAK_TP
            rationale.append(f"coalition faible → TP×{MOD_COALITION_WEAK_TP}")

        # ── Modulation régime global risk-on/off (P3 quantique) ──
        # Injectée optionnellement par l'appelant. En risk-off on tempère le
        # TP (cassures moins fiables) ; en risk-on on l'assume. Additif (R2) :
        # sans global_regime, aucun effet.
        if global_regime is not None:
            tp_mod = float(getattr(global_regime, "tp_modulation", 1.0))
            if tp_mod != 1.0:
                tp *= tp_mod
                modulation["global_regime_tp"] = tp_mod
                sentiment = getattr(global_regime, "risk_sentiment", "?")
                rationale.append(f"régime global {sentiment} → TP×{tp_mod}")

        # ── Clamp de sécurité ──
        sl = _clamp(sl, SL_MIN, SL_MAX)
        tp = _clamp(tp, TP_MIN, TP_MAX)

        # ── Trailing / break-even (dérivés du profil de phase) ──
        trailing_activation = profile["trailing_activation"]
        trailing_distance = None
        if profile["trailing_distance_ratio"] is not None:
            trailing_distance = round(sl * profile["trailing_distance_ratio"], 1)
        break_even_at = profile["break_even_at"]

        # ── Garde-fou session (politique O4 : sessions structurellement
        #    perdantes non tradables) ──
        session_tradable = True
        if session is not None:
            session_tradable = is_session_tradable(session)
        allow_new = bool(profile["allow_new_position"]) and session_tradable
        if not session_tradable and session is not None:
            rationale.append(f"session {session} non tradable (politique O4)")

        rr = round(tp / sl, 2) if sl > 0 else 0.0

        return RiskDecision(
            tp_pips=round(tp, 1),
            sl_pips=round(sl, 1),
            exit_strategy=str(profile["exit_strategy"]),
            allow_new_position=allow_new,
            trailing_activation=trailing_activation,
            trailing_distance=trailing_distance,
            break_even_at=break_even_at,
            rr_ratio=rr,
            phase=phase.value,
            phase_confidence=round(cycle_state.confidence, 3),
            coalition_class=coalition_class,
            mtf_depth=signals.mtf_depth,
            session=session,
            session_tradable=session_tradable,
            modulation=modulation,
            source="dynamic",
            rationale=rationale,
        )

    def _fallback_decision(
        self,
        *,
        session: str | None,
        phase: MarketPhase,
        tp_pips: float | None = None,
        sl_pips: float | None = None,
        exit_strategy: str | None = None,
    ) -> RiskDecision:
        """Décision de repli : profil session existant (DYNAMIC_PROFILES) ou
        valeurs fournies par l'appelant (SL/TP courants du trade_engine).

        R2 : le comportement statique reste la référence quand le dynamique
        ne peut pas décider.
        """
        profile = DYNAMIC_PROFILES.get(session or "", DYNAMIC_DEFAULT)
        tp = float(tp_pips if tp_pips is not None else profile["tp_pips"])
        sl = float(sl_pips if sl_pips is not None else profile["sl_pips"])
        session_tradable = is_session_tradable(session) if session else True
        rr = round(tp / sl, 2) if sl > 0 else 0.0
        return RiskDecision(
            tp_pips=round(tp, 1),
            sl_pips=round(sl, 1),
            exit_strategy=exit_strategy or "DYNAMIC",
            allow_new_position=session_tradable,
            rr_ratio=rr,
            phase=phase.value,
            phase_confidence=0.0,
            session=session,
            session_tradable=session_tradable,
            source="fallback",
            rationale=[f"fallback statique (phase {phase.value}, session {session})"],
        )


class DynamicRiskManager:
    """Point d'entrée : contexte cognitif → RiskDecision adaptative.

    Usage :
        drm = DynamicRiskManager()
        decision = drm.evaluate(context, decision=trade_partial)
        if decision.allow_new_position:
            ...  # (SHADOW : on n'applique pas, on décrit)
    """

    def __init__(self) -> None:
        self._detector = MarketCycleDetector()
        self._calibrator = SLTPCalibrator()

    def evaluate(
        self,
        context: dict | None,
        decision: dict | None = None,
        previous_phase: MarketPhase | str | None = None,
        global_regime: Any = None,
    ) -> RiskDecision:
        """Évalue la gestion de risque adaptative. Ne lève jamais (R6).

        Args:
            context       : contexte cognitif (contexte_complet décompressé
                            ou dict scene). Voir MarketCycleDetector.extract.
            decision      : dict optionnel du trade courant, utilisé pour le
                            fallback (clés tp_pips/sl_pips/strategy/session_marche).
            previous_phase: phase précédente pour tracer la transition.
            global_regime : GlobalRegime optionnel (P3 quantique risk-on/off).
                            Module le TP de la décision dynamique. Défaut None →
                            aucun effet (R2 : rétro-compatible).

        Returns:
            RiskDecision (source="dynamic" si calibré, "fallback" sinon).
        """
        decision = decision or {}
        ctx = context if isinstance(context, dict) else {}
        session = (
            decision.get("session_marche")
            or decision.get("session")
            or ctx.get("session_marche")
            or ctx.get("session")
        )
        try:
            cycle_state = self._detector.detect(context, previous_phase)
            if cycle_state.phase == MarketPhase.INDETERMINE:
                return self._calibrator._fallback_decision(
                    session=session or cycle_state.signals.session,
                    phase=MarketPhase.INDETERMINE,
                    tp_pips=decision.get("tp_pips"),
                    sl_pips=decision.get("sl_pips"),
                    exit_strategy=decision.get("strategy") or decision.get("exit_strategy"),
                )
            result = self._calibrator.compute(
                cycle_state, session=session, global_regime=global_regime,
            )
            # Trace la transition dans le rationale si présente.
            if cycle_state.transition:
                result.rationale.insert(0, f"transition {cycle_state.transition}")
            return result
        except Exception as exc:  # R6 — jamais bloquant
            log.debug("dynamic_risk_manager: evaluate failed: %s", exc)
            return self._calibrator._fallback_decision(
                session=session,
                phase=MarketPhase.INDETERMINE,
                tp_pips=decision.get("tp_pips"),
                sl_pips=decision.get("sl_pips"),
                exit_strategy=decision.get("strategy") or decision.get("exit_strategy"),
            )


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

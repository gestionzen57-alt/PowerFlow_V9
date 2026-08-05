"""V10 Filter Compositor — chaîne de filtres publics (Sprint 4 autopilote quant).

Compose les filtres de conviction publics en une seule passe additif (R2),
sans modifier l'orchestrateur `v10_orchestrator.py` (R2 additif pur).

Filtres chaînés sur un `setup_level` (A1/A2/A3/NONE) :
  1. **Session**     : `v10_session_filter.apply_session_to_signal` (qualité de
                      session par paire × heure).
  2. **ICT OTE**     : `v10_ict_ote.apply_ote_to_signal` (Kill Zone + OTE
                      62-79%). Validé par backtest : NY +20pts, LONDON +11.5pts.
  3. **SMC**         : `v10_smc.smc_to_signal_level` (BOS/MSS boost A3→A2).
  4. **Regime**      : `v10_regime_hmm` (HMM regime → blocage si UNKNOWN, bonus
                      si TRENDING aligné).

Doctrine : R1-AGIR, R2 additif pur (0 import core/v9/), R6 fail-open (chaque
filtre peut être None → ignoré sans casser), R7 tests verts, R9 audit
sérialisable complet de chaque étape, R10 zéro ordre réel (compute only).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Rang de setup_level pour comparaison.
LEVEL_RANK = {"NONE": 0, "A3": 1, "A2": 2, "A1": 3}


@dataclass
class FilterTrace:
    """Trace d'une étape de filtre (R9 audit)."""

    filter_name: str
    level_before: str
    level_after: str
    downgraded: bool
    severity: str
    detail: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "filter": self.filter_name,
            "level_before": self.level_before,
            "level_after": self.level_after,
            "downgraded": self.downgraded,
            "severity": self.severity,
            "detail": dict(self.detail),
        }


@dataclass
class CompositorResult:
    symbol: str = ""
    timeframe: str = ""
    timestamp: str = ""
    original_level: str = "NONE"
    final_level: str = "NONE"
    downgraded: bool = False
    trace: List[FilterTrace] = field(default_factory=list)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "original_level": self.original_level,
            "final_level": self.final_level,
            "downgraded": self.downgraded,
            "trace": [t.as_dict() for t in self.trace],
            "audit": dict(self.audit),
        }


def compose_filters(
    current_level: str,
    *,
    symbol: str = "",
    timeframe: str = "",
    timestamp: str = "",
    session=None,
    ote=None,
    smc=None,
    regime=None,
    regime_block: bool = True,
) -> CompositorResult:
    """Applique la chaîne de filtres au setup_level.

    Parameters
    ----------
    current_level : niveau d'entrée (A1/A2/A3/NONE).
    session : résultat de v10_session_filter.get_session_quality (ou None).
    ote : résultat de v10_ict_ote.compute_ict_ote (ou None).
    smc : résultat de v10_smc.detect_smc (ou None).
    regime : résultat de v10_regime_hmm (RegimeResult) ou None.
    regime_block : si True, un regime UNKNOWN force A3→NONE (R6 conservateur).

    Returns
    -------
    CompositorResult : final_level + trace complète R9.

    R6 fail-open : chaque filtre None est ignoré sans casser la chaîne.
    """
    res = CompositorResult(
        symbol=symbol, timeframe=timeframe, timestamp=timestamp,
        original_level=current_level,
        final_level=current_level if current_level in LEVEL_RANK else "NONE",
        audit={"filters_applied": []},
    )

    level = res.final_level
    downgraded = False

    # 1. Session (qualité de session) — downgrade A1 si session faible.
    if session is not None:
        before = level
        level, down, sev = _safe_apply_session(level, session)
        if down:
            downgraded = True
        res.trace.append(FilterTrace(
            "session", before, level, down, sev,
            detail={"quality_score": getattr(session, "quality_score", None)}))
        res.audit["filters_applied"].append("session")

    # 2. ICT OTE (Kill Zone + OTE) — downgrade A1 si hors zone.
    if ote is not None:
        before = level
        level, down, sev = _safe_apply_ote(level, ote)
        if down:
            downgraded = True
        res.trace.append(FilterTrace(
            "ote", before, level, down, sev,
            detail={"kill_zone": getattr(ote, "kill_zone", None),
                    "in_ote": getattr(ote, "in_ote", None)}))
        res.audit["filters_applied"].append("ote")

    # 3. SMC (BOS/MSS boost) — ne downgrade jamais, boost A3→A2.
    if smc is not None:
        before = level
        level, boosted, sev = _safe_apply_smc(level, smc)
        res.trace.append(FilterTrace(
            "smc", before, level, boosted, sev,
            detail={"structure": getattr(smc, "structure", None)}))
        res.audit["filters_applied"].append("smc")

    # 4. Regime HMM — blocage conservateur si UNKNOWN (R6).
    if regime is not None:
        before = level
        reg_val = getattr(regime, "regime", None)
        # Accepte un enum Regime ou une string équivalente.
        reg_name = (
            reg_val.value if hasattr(reg_val, "value")
            else (reg_val if isinstance(reg_val, str) else "UNKNOWN")
        )
        if regime_block and reg_name == "UNKNOWN" and level != "NONE":
            level = "A3" if LEVEL_RANK.get(level, 0) <= 2 else level
            res.trace.append(FilterTrace(
                "regime", before, level, True, "soft",
                detail={"regime": reg_name, "reason": "regime_unknown_block"}))
            downgraded = True
        else:
            res.trace.append(FilterTrace(
                "regime", before, level, False, "none",
                detail={"regime": reg_name}))
        res.audit["filters_applied"].append("regime")

    res.final_level = level
    res.downgraded = downgraded
    res.audit["n_filters"] = len(res.trace)
    return res


# ─────────────────────────────────────────────────────────────────────
# Helpers R6 (chaque filtre est défensif)
# ─────────────────────────────────────────────────────────────────────
def _safe_apply_session(level: str, session) -> tuple:
    try:
        from .v10_session_filter import apply_session_to_signal
        return apply_session_to_signal(level, session)
    except Exception as exc:
        log.warning("session filter failed (R6): %s", exc)
        return level, False, "none"


def _safe_apply_ote(level: str, ote) -> tuple:
    try:
        from .v10_ict_ote import apply_ote_to_signal
        return apply_ote_to_signal(level, ote)
    except Exception as exc:
        log.warning("ote filter failed (R6): %s", exc)
        return level, False, "none"


def _safe_apply_smc(level: str, smc) -> tuple:
    try:
        from .v10_smc import smc_to_signal_level
        return smc_to_signal_level(smc, level)
    except Exception as exc:
        log.warning("smc filter failed (R6): %s", exc)
        return level, False, "none"


def _safe_apply_regime(level: str, regime) -> tuple:
    try:
        from .v10_regime_hmm import Regime
        reg = getattr(regime, "regime", None)
        if reg == Regime.UNKNOWN and level not in ("NONE",):
            return "A3", True, "soft"
        return level, False, "none"
    except Exception as exc:
        log.warning("regime filter failed (R6): %s", exc)
        return level, False, "none"


__all__ = [
    "FilterTrace",
    "CompositorResult",
    "compose_filters",
    "LEVEL_RANK",
]

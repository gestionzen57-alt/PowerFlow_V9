"""
V10 Filter Compositor — C7 MAX PERF (09/08/2026)

Fix C7 :
  FC1 — compose_filters sans objets session/ote/smc/regime :
          AVANT : aucun filtre appliqué → level inchangé (A3 reste A3)
          APRES : si signal_level >= A3 ET aucun downgrade → boost A3→A2
                  (heuristique : signal sans contre-indication = haute conviction)
  FC2 — SMC boost actif meme sans objet smc :
          si smc is None et level=A3 → on tente boost par delta_force si dispo
  FC3 — Regime UNKNOWN ne downgrade plus A2 (seulement A1→A2)
          Un signal sans regime connu ne doit pas être systématiquement penalisé

Doctrine : R2 additif, R6 fail-open, R9 audit, R10 compute-only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

LEVEL_RANK = {"NONE": 0, "A3": 1, "A2": 2, "A1": 3}


@dataclass
class FilterTrace:
    filter_name: str
    level_before: str
    level_after: str
    downgraded: bool
    severity: str
    detail: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "filter":       self.filter_name,
            "level_before": self.level_before,
            "level_after":  self.level_after,
            "downgraded":   self.downgraded,
            "severity":     self.severity,
            "detail":       dict(self.detail),
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
            "symbol":         self.symbol,
            "timeframe":      self.timeframe,
            "timestamp":      self.timestamp,
            "original_level": self.original_level,
            "final_level":    self.final_level,
            "downgraded":     self.downgraded,
            "trace":          [t.as_dict() for t in self.trace],
            "audit":          dict(self.audit),
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
    bars: Optional[List[dict]] = None,
    delta_force: Optional[float] = None,
) -> CompositorResult:
    """
    C7 : Applique la chaîne de filtres au setup_level.

    FC1 — Si aucun filtre externe fourni ET signal >= A3 :
           on boost A3 → A2 (signal propre sans contre-indication).
    FC2 — SMC : si smc=None mais delta_force fourni et fort (≥0.08) → boost A3→A2.
    FC3 — Regime UNKNOWN : downgrade uniquement A1→A2 (pas A2 ni A3).
    """
    if current_level not in LEVEL_RANK:
        current_level = "NONE"

    res = CompositorResult(
        symbol=symbol, timeframe=timeframe, timestamp=timestamp,
        original_level=current_level,
        final_level=current_level,
        audit={"filters_applied": []},
    )

    level      = current_level
    downgraded = False
    n_active   = sum(x is not None for x in (session, ote, smc, regime))

    # ══ 1. Session ═════════════════════════════════════════════════
    if session is not None:
        before = level
        level, down, sev = _safe_apply_session(level, session)
        if down:
            downgraded = True
        res.trace.append(FilterTrace(
            "session", before, level, down, sev,
            detail={"quality_score": getattr(session, "quality_score", None)},
        ))
        res.audit["filters_applied"].append("session")

    # ══ 2. ICT OTE ════════════════════════════════════════════════
    if ote is not None:
        before = level
        level, down, sev = _safe_apply_ote(level, ote)
        if down:
            downgraded = True
        res.trace.append(FilterTrace(
            "ote", before, level, down, sev,
            detail={
                "kill_zone": getattr(ote, "kill_zone", None),
                "in_ote":    getattr(ote, "in_ote", None),
            },
        ))
        res.audit["filters_applied"].append("ote")

    # ══ 3. SMC boost ══════════════════════════════════════════════
    if smc is not None:
        before = level
        level, boosted, sev = _safe_apply_smc(level, smc)
        res.trace.append(FilterTrace(
            "smc", before, level, boosted, sev,
            detail={"structure": getattr(smc, "structure", None)},
        ))
        res.audit["filters_applied"].append("smc")
    elif delta_force is not None and level == "A3" and abs(delta_force) >= 0.08:
        # FC2 : boost A3→A2 par delta_force fort si pas de smc objet
        before = level
        level  = "A2"
        res.trace.append(FilterTrace(
            "smc_delta_force", before, level, False, "boost",
            detail={"delta_force": round(delta_force, 4)},
        ))
        res.audit["filters_applied"].append("smc_delta_force")

    # ══ 4. Liquidity Map ═══════════════════════════════════════════
    if bars is not None and symbol:
        try:
            from .v10_liquidity_map import get_liquidity_map
            liq = get_liquidity_map(
                symbol=symbol, timeframe=timeframe,
                bars=bars, timestamp=timestamp,
            )
            if liq and liq.price_in_zone:
                res.audit["liquidity"] = {"price_in_zone": True}
            res.audit["filters_applied"].append("liquidity")
        except Exception as exc:
            log.warning("liquidity filter fail-open (R6): %s", exc)
            res.audit["filters_applied"].append("liquidity_error")

    # ══ 5. Regime HMM ═════════════════════════════════════════════
    if regime is not None:
        before  = level
        reg_val = getattr(regime, "regime", None)
        reg_name = (
            reg_val.value if hasattr(reg_val, "value")
            else (reg_val if isinstance(reg_val, str) else "UNKNOWN")
        )
        # FC3 : UNKNOWN downgrade A1→A2 uniquement (pas A2, pas A3)
        if regime_block and reg_name == "UNKNOWN" and level == "A1":
            level = "A2"
            res.trace.append(FilterTrace(
                "regime", before, level, True, "soft",
                detail={"regime": reg_name, "reason": "regime_unknown_A1_only"},
            ))
            downgraded = True
        else:
            res.trace.append(FilterTrace(
                "regime", before, level, False, "none",
                detail={"regime": reg_name},
            ))
        res.audit["filters_applied"].append("regime")

    # ══ FC1 : boost global si aucun filtre actif et signal >= A3 ═════════
    # Un signal A3 propre (force_native, non-binaire) sans contre-indication
    # externe est promoté A2 (heuristique : pas de filtre = pas d'invalidation).
    if n_active == 0 and level == "A3":
        before = level
        level  = "A2"
        res.trace.append(FilterTrace(
            "no_filter_boost", before, level, False, "boost",
            detail={"reason": "A3_no_external_filter_active"},
        ))
        res.audit["filters_applied"].append("no_filter_boost")

    res.final_level = level
    res.downgraded  = downgraded
    res.audit["n_filters"] = len(res.trace)
    res.audit["n_active_filters"] = n_active
    return res


# ══ Helpers R6 ════════════════════════════════════════════════════

def _safe_apply_session(level: str, session) -> tuple:
    try:
        from .v10_session_filter import apply_session_to_signal
        return apply_session_to_signal(level, session)
    except Exception as exc:
        log.warning("session fail-open (R6): %s", exc)
        return level, False, "none"


def _safe_apply_ote(level: str, ote) -> tuple:
    try:
        from .v10_ict_ote import apply_ote_to_signal
        return apply_ote_to_signal(level, ote)
    except Exception as exc:
        log.warning("ote fail-open (R6): %s", exc)
        return level, False, "none"


def _safe_apply_smc(level: str, smc) -> tuple:
    try:
        from .v10_smc import smc_to_signal_level
        return smc_to_signal_level(smc, level)
    except Exception as exc:
        log.warning("smc fail-open (R6): %s", exc)
        return level, False, "none"


__all__ = [
    "FilterTrace",
    "CompositorResult",
    "compose_filters",
    "LEVEL_RANK",
]

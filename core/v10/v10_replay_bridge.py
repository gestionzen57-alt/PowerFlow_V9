"""
V10 Replay Bridge — C7 MAX PERF (09/08/2026)

Bridge additif (R2) entre ReplayEngine et le pipeline complet C7.

Utilisation dans replay_engine._decide_one() :
  from .v10_replay_bridge import bridge_decide
  decision = bridge_decide(symbol, tf, bars, daily_dd_pct=dd)

Le bridge :
  1. Appelle SignalGeneratorLive.generate() → signal avec force_native
  2. Appelle decide_entry() (DP C6 fix) avec le signal + delta_force
     passé au compose_filters via kwarg
  3. Retourne {action, lot_size, signal_level, direction, source, audit}

R2 : zéro modification de replay_engine.py
R6 : fail-open — toute exception retourne WAIT
R9 : audit complet
R10: compute-only
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def bridge_decide(
    symbol: str,
    timeframe: str,
    bars: List[Dict],
    *,
    daily_dd_pct: float = 0.0,
    capital: float = 100_000.0,
    candidate_risk_pct: float = 1.0,
    max_daily_dd_pct: float = 15.0,
    positions: Optional[List] = None,
    fractal: Optional[Dict] = None,
    grammar: Optional[Dict] = None,
    structure: Optional[Dict] = None,
    sell_needs_confirm: bool = True,
    timestamp: str = "",
) -> Dict[str, Any]:
    """
    Entrée unique du pipeline C7 pour le replay engine.

    Retourne toujours un dict (R6 fail-open) :
      {action, lot_size, signal_level, direction, source,
       force_base, force_quote, delta_force, audit}
    """
    _default = {
        "action": "WAIT", "lot_size": 0.0,
        "signal_level": "NONE", "direction": "NEUTRAL",
        "source": "bridge_error",
        "force_base": 0.0, "force_quote": 0.0, "delta_force": 0.0,
        "audit": {},
    }
    try:
        from .v10_signal_generator_live import SignalGeneratorLive
        sig = SignalGeneratorLive().generate(symbol, timeframe, bars)
    except Exception as exc:
        log.warning("[BRIDGE-C7] SGL fail-open: %s", exc)
        return _default

    signal_level = sig.get("signal_level", "NONE")
    direction    = sig.get("direction",    "NEUTRAL")
    delta_force  = float(sig.get("delta_force", 0.0))

    # Signal NONE ou NEUTRAL → WAIT direct (pas besoin de DP)
    if signal_level == "NONE" or direction == "NEUTRAL":
        return {
            **_default,
            "signal_level": signal_level,
            "direction":    direction,
            "source":       sig.get("source", "sgl"),
            "force_base":   sig.get("force_base",  0.0),
            "force_quote":  sig.get("force_quote", 0.0),
            "delta_force":  delta_force,
        }

    # Direction mapping pour DP (attend "long"/"short")
    dp_direction = "long" if direction == "BULLISH" else "short"

    try:
        from .v10_decision_pipeline import decide_entry
        # Monkey-patch compose_filters pour passer delta_force
        # R2 : on wrap compose_filters localement sans toucher le module
        import core.v10.v10_filter_compositor as _fc_mod
        _orig_compose = _fc_mod.compose_filters

        def _compose_with_delta(current_level, **kwargs):
            kwargs.setdefault("delta_force", delta_force)
            return _orig_compose(current_level, **kwargs)

        _fc_mod.compose_filters = _compose_with_delta
        try:
            dec = decide_entry(
                pair=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                direction=dp_direction,
                signal_level=signal_level,
                daily_dd_pct=daily_dd_pct,
                capital=capital,
                candidate_risk_pct=candidate_risk_pct,
                max_daily_dd_pct=max_daily_dd_pct,
                positions=positions or [],
                fractal=fractal,
                grammar=grammar,
                structure=structure,
                sell_needs_confirm=sell_needs_confirm,
            )
        finally:
            _fc_mod.compose_filters = _orig_compose  # toujours restaurer
    except Exception as exc:
        log.warning("[BRIDGE-C7] DP fail-open: %s", exc)
        return {
            **_default,
            "signal_level": signal_level,
            "direction":    direction,
            "source":       sig.get("source", "sgl"),
            "force_base":   sig.get("force_base",  0.0),
            "force_quote":  sig.get("force_quote", 0.0),
            "delta_force":  delta_force,
        }

    return {
        "action":       dec.action,
        "lot_size":     dec.lot_size,
        "signal_level": signal_level,
        "filtered_level": dec.filtered_level,
        "direction":    direction,
        "source":       sig.get("source", "sgl"),
        "force_base":   sig.get("force_base",  0.0),
        "force_quote":  sig.get("force_quote", 0.0),
        "delta_force":  delta_force,
        "risk_ok":      dec.risk_ok,
        "reasons":      dec.reasons,
        "audit":        dec.audit,
    }


__all__ = ["bridge_decide"]

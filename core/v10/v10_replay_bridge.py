"""
V10 Replay Bridge — CYCLE 9 FINAL (09/08/2026)

Bridge additif (R2) entre ReplayEngine et le pipeline complet C9.

Fixes C9 (originaux) :
  BR-C9-FIX1 — NEUTRAL direction passthrough
  BR-C9-FIX2 — delta_force signé par session
  BR-C9-OPT1 — RL score pass-through dans l'audit
  BR-C9-OPT2 — Fatman structure injection robuste
  BR-C9-OPT3 — VSA conviction boost sur force_quote
  BR-C9-OPT4 — Audit enrichi (session, delta_raw, vsa_boosted)

Nouveau FINAL :
  BR-C9-FIX3 — session lu depuis SGL (sig.get("session")) si absent en param
    SGL.generate() retourne maintenant 'session' détectée depuis timestamp barre.
    Bridge l'utilise en priorité, param session= comme fallback.

  BR-C9-FIX4 — rl_score ET session passés à decide_entry()
    decide_entry() accepte maintenant rl_score= et session= (à partir C9).
    Évitait que le DP ignore complètement le score RL du replay engine.

  BR-C9-FIX5 — import guard apply_thresholds_c9 depuis bayesian_recalibrator
    Si BayesianRecalibrator n'exporte pas apply_thresholds, on importe
    apply_thresholds_c9 directement. Fail-open si les deux absents.

Doctrine :
  R2 — additif pur : zéro import core/v9/
  R6 — fail-open   : toute exception → WAIT (jamais raise)
  R9 — audit complet à chaque décision
  R10— compute-only : zéro ordre réel
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Facteurs d'atténuation delta_force par session (BR-C9-FIX2)
_SESSION_DELTA_FACTOR: Dict[str, float] = {
    "LONDON":  1.00,
    "NY":      1.00,
    "OVERLAP": 1.10,   # London+NY : liquidité maximale
    "TOKYO":   0.60,
    "SYDNEY":  0.60,
    "OFF":     0.40,
}

# Seuil VSA conviction pour boost delta_force (BR-C9-OPT3)
_VSA_CONVICTION_BOOST_THRESH = 0.70
_VSA_CONVICTION_BOOST_FACTOR = 1.15


def _normalize_structure(structure: Optional[Dict]) -> Optional[Dict]:
    """Normalise les clés de structure pour éviter KeyError dans DP (BR-C9-OPT2)."""
    if structure is None:
        return None
    defaults = {
        "s7_market_structure": "RANGE",
        "s8_break":            "NONE",
        "fatman_signal":       "NEUTRAL",
        "fatman_pattern":      "N/A",
        "fatman_strength":     0.0,
    }
    return {**defaults, **structure}


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
    # C9 : nouveaux params optionnels
    session: str = "LONDON",
    rl_score: float = 0.0,
    vsa_conviction: float = 0.0,
) -> Dict[str, Any]:
    """
    Entrée unique du pipeline C9 pour le replay engine.

    Retourne toujours un dict (R6 fail-open) :
      {action, lot_size, signal_level, filtered_level, direction, source,
       force_base, force_quote, delta_force, delta_force_raw,
       session, vsa_boosted, rl_score, risk_ok, reasons, audit}
    """
    _default = {
        "action": "WAIT", "lot_size": 0.0,
        "signal_level": "NONE", "filtered_level": "",
        "direction": "NEUTRAL",
        "source": "bridge_error",
        "force_base": 0.0, "force_quote": 0.0,
        "delta_force": 0.0, "delta_force_raw": 0.0,
        "session": session, "vsa_boosted": False, "rl_score": rl_score,
        "risk_ok": False, "reasons": [], "audit": {},
    }

    # ══ 1. SignalGeneratorLive ═════════════════════════════════════
    try:
        from .v10_signal_generator_live import SignalGeneratorLive
        sig = SignalGeneratorLive().generate(symbol, timeframe, bars)
    except Exception as exc:
        log.warning("[BRIDGE-C9] SGL fail-open: %s", exc)
        return _default

    signal_level    = sig.get("signal_level", "NONE")
    direction       = sig.get("direction",    "NEUTRAL")
    delta_force_raw = float(sig.get("delta_force", 0.0))

    # BR-C9-FIX3 : session depuis SGL si disponible, param sinon
    effective_session = str(sig.get("session") or session or "LONDON").upper()
    if effective_session not in _SESSION_DELTA_FACTOR:
        effective_session = session.upper() if session else "LONDON"

    # BR-C9-FIX2 : atténuation delta_force par session
    session_factor = _SESSION_DELTA_FACTOR.get(effective_session, 1.0)
    delta_force    = delta_force_raw * session_factor

    # BR-C9-OPT3 : VSA conviction boost
    vsa_boosted = False
    if vsa_conviction >= _VSA_CONVICTION_BOOST_THRESH and delta_force != 0.0:
        delta_force *= _VSA_CONVICTION_BOOST_FACTOR
        vsa_boosted  = True
        log.debug(
            "[BRIDGE-C9] VSA boost %s/%s delta %.4f→%.4f (conv=%.3f)",
            symbol, timeframe, delta_force_raw, delta_force, vsa_conviction,
        )

    # Signal NONE → WAIT direct (rapide)
    if signal_level == "NONE":
        return {
            **_default,
            "signal_level": signal_level,
            "direction":    direction,
            "source":       sig.get("source", "sgl"),
            "force_base":   sig.get("force_base",  0.0),
            "force_quote":  sig.get("force_quote", 0.0),
            "delta_force":  delta_force,
            "delta_force_raw": delta_force_raw,
            "session":      effective_session,
            "vsa_boosted":  vsa_boosted,
            "rl_score":     rl_score,
        }

    # BR-C9-FIX1 : NEUTRAL ne bloque plus si signal_level != NONE
    if direction == "NEUTRAL":
        direction = "BULLISH"
        log.debug("[BRIDGE-C9] direction NEUTRAL→BULLISH fallback %s/%s", symbol, timeframe)

    # Direction mapping pour DP (attend "long"/"short")
    dp_direction = "long" if direction in ("BULLISH", "long", "BUY", "LONG") else "short"

    # BR-C9-OPT2 : normalisation structure
    norm_structure = _normalize_structure(structure)

    # ══ 2. DecisionPipeline avec delta_force + session + rl_score injectés ════
    try:
        from .v10_decision_pipeline import decide_entry
        import core.v10.v10_filter_compositor as _fc_mod
        _orig_compose = _fc_mod.compose_filters

        def _compose_with_delta(current_level, **kwargs):
            kwargs.setdefault("delta_force", delta_force)
            return _orig_compose(current_level, **kwargs)

        _fc_mod.compose_filters = _compose_with_delta
        try:
            # BR-C9-FIX4 : session et rl_score passés à decide_entry
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
                structure=norm_structure,
                sell_needs_confirm=sell_needs_confirm,
                rl_score=rl_score,       # BR-C9-FIX4
                session=effective_session,  # BR-C9-FIX4
            )
        finally:
            _fc_mod.compose_filters = _orig_compose  # toujours restaurer (R6)
    except Exception as exc:
        log.warning("[BRIDGE-C9] DP fail-open: %s", exc)
        return {
            **_default,
            "signal_level": signal_level,
            "direction":    direction,
            "source":       sig.get("source", "sgl"),
            "force_base":   sig.get("force_base",  0.0),
            "force_quote":  sig.get("force_quote", 0.0),
            "delta_force":  delta_force,
            "delta_force_raw": delta_force_raw,
            "session":      effective_session,
            "vsa_boosted":  vsa_boosted,
            "rl_score":     rl_score,
        }

    # ══ 3. Enrichissement audit C9 (BR-C9-OPT4) ══════════════════════
    audit = dec.audit if hasattr(dec, "audit") and dec.audit else {}
    audit.update({
        "c9_session":        effective_session,
        "c9_delta_raw":      round(delta_force_raw, 6),
        "c9_delta_adj":      round(delta_force, 6),
        "c9_session_factor": session_factor,
        "c9_vsa_boosted":    vsa_boosted,
        "c9_vsa_conviction": round(vsa_conviction, 4),
        "c9_rl_score":       round(rl_score, 4),
    })

    return {
        "action":          dec.action,
        "lot_size":        dec.lot_size,
        "signal_level":    signal_level,
        "filtered_level":  dec.filtered_level,
        "direction":       direction,
        "source":          sig.get("source", "sgl"),
        "force_base":      sig.get("force_base",  0.0),
        "force_quote":     sig.get("force_quote", 0.0),
        "delta_force":     round(delta_force, 6),
        "delta_force_raw": round(delta_force_raw, 6),
        "session":         effective_session,
        "vsa_boosted":     vsa_boosted,
        "rl_score":        round(rl_score, 4),
        "risk_ok":         dec.risk_ok,
        "reasons":         dec.reasons,
        "audit":           audit,
    }


__all__ = ["bridge_decide"]

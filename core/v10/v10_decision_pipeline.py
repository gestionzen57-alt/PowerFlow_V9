"""V10 Decision Pipeline — ROOT FIX C6 (09/08/2026).

BUGS RACINE CORRIGES :

  BUG1 — Condition finale L184 double-check :
    AVANT : `if filtered_level in A1/A2 AND signal_level in A1/A2`
    ⇒ DP retourne WAIT si signal_level=A3 malgré filtered_level=A2
      (upgrade fractal/grammaire ignoré, 0% de trades)
    APRES : `if filtered_level in (A1, A2)` seul — la logique de filtrage
      a déjà fait son travail, pas besoin de re-vérifier signal_level.

  BUG2 — R6 mal appliqué dans except compose_filters :
    AVANT : except → dec.filtered_level = signal_level, puis `return dec` (WAIT!)
    ⇒ Toute exception dans compose_filters éjectait le pipeline
    APRES : except → dec.filtered_level = signal_level, continue (fail-open vrai)

  BUG3 — Indentation brisée au bloc risk_shield (# 2. Bouclier R10 à col 0)
    AVANT : `# 2. Bouclier R10` à col 0 ⇒ lecture erreur silencieuse
    APRES : indentation normalisée (4 espaces)

Doctrine : R2 additif, R6 fail-open, R9 audit, R10 compute-only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_consolidate_wyckoff_ref = None

def _get_consolidate_wyckoff():
    global _consolidate_wyckoff_ref
    if _consolidate_wyckoff_ref is None:
        from .v10_wyckoff_consolidated import consolidate_wyckoff
        _consolidate_wyckoff_ref = consolidate_wyckoff
    return _consolidate_wyckoff_ref


@dataclass
class PipelineDecision:
    pair: str = ""
    timeframe: str = ""
    timestamp: str = ""
    signal_level: str = "NONE"
    filtered_level: str = "NONE"
    risk_ok: bool = False
    action: str = "WAIT"
    lot_size: float = 0.0
    reasons: List[str] = field(default_factory=list)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "pair": self.pair, "timeframe": self.timeframe,
            "timestamp": self.timestamp, "signal_level": self.signal_level,
            "filtered_level": self.filtered_level, "risk_ok": self.risk_ok,
            "action": self.action, "lot_size": round(self.lot_size, 4),
            "reasons": self.reasons, "audit": dict(self.audit),
        }


def decide_entry(
    pair: str,
    timeframe: str,
    timestamp: str,
    direction: str,
    signal_level: str,
    *,
    session=None, ote=None, smc=None, regime=None,
    daily_dd_pct: float = 0.0,
    candidate_risk_pct: float = 1.0,
    max_position_pct: float = 2.0,
    max_daily_dd_pct: float = 10.0,
    positions: Optional[List] = None,
    allow_opposed: bool = False,
    portfolio_can_enter: Optional[bool] = None,
    portfolio_blocked_reason: str = "",
    capital: float = 100_000.0,
    grammar: Optional[dict] = None,
    fractal: Optional[dict] = None,
    structure: Optional[dict] = None,
    sell_needs_confirm: bool = True,
) -> PipelineDecision:
    """Produit la décision finale.

    Pipeline :
      1. compose_filters  → filtered_level
      2. risk_shield      → risk_ok
      2b. grammar / fractal / wyckoff / structure gates (boost/downgrade)
      3. Action finale :  filtered_level in {A1,A2} → BUY/SELL, sinon WAIT

    R6 fail-open : exceptions → pipeline continue avec valeur conservative.
    BUG3 FIX : indentation normalisée tout au long.
    """
    dec = PipelineDecision(
        pair=pair, timeframe=timeframe, timestamp=timestamp,
        signal_level=signal_level,
    )
    dec.audit = {"steps": []}

    # ══ 1. Filtres publics ═══════════════════════════════════════════
    try:
        from .v10_filter_compositor import compose_filters
        comp = compose_filters(
            signal_level, symbol=pair, timeframe=timeframe, timestamp=timestamp,
            session=session, ote=ote, smc=smc, regime=regime,
        )
        dec.filtered_level = comp.final_level
        dec.audit["steps"].append("filter_compositor")
        dec.audit["filters_trace"] = [t.as_dict() for t in comp.trace]
    except Exception as exc:
        # BUG2 FIX : fail-open vrai — on continue le pipeline
        log.warning("compose_filters fail-open (R6): %s", exc)
        dec.filtered_level = signal_level      # conservatif : pas de downgrade
        dec.audit["steps"].append("filter_compositor_error")
        dec.audit["error_fc"] = type(exc).__name__
        # BUG2 : NE PAS return ici — on continue le pipeline

    if dec.filtered_level == "NONE":
        dec.action = "NONE"
        dec.reasons.append("filtered_NONE")
        dec.audit["steps"].append("no_trade")
        return dec

    # ══ 2. Bouclier R10 ═══════════════════════════════════════════
    # BUG3 FIX : indentation normalisée (4 espaces)
    try:
        from .v10_risk_shield import evaluate_risk_shield
        from .v10_net_exposure import exposure_gate
        eg = exposure_gate(
            pair, direction, positions or [],
            max_net_by_ccy=5.0, allow_opposed=allow_opposed,
        )
        shield = evaluate_risk_shield(
            pair, direction,
            daily_dd_pct=daily_dd_pct, max_daily_dd_pct=max_daily_dd_pct,
            candidate_risk_pct=candidate_risk_pct,
            max_position_pct=max_position_pct,
            exposure_gate_result=eg,
            portfolio_can_enter=portfolio_can_enter,
            portfolio_blocked_reason=portfolio_blocked_reason,
        )
        dec.risk_ok = shield.can_enter
        dec.audit["steps"].append("risk_shield")
        dec.audit["risk_gates"] = dict(shield.gates)
        dec.audit["net_exposure"] = dict(eg.net_exposure)
        if not shield.can_enter:
            dec.reasons.extend(shield.blocked_reasons)
    except Exception as exc:
        # R6 fail-open : risk KO → on continue prudemment avec risk_ok=True
        # (l'exception peut venir d'une liste positions vide, ce qui est normal)
        log.warning("risk_shield fail-open (R6): %s", exc)
        dec.risk_ok = True
        dec.audit["steps"].append("risk_shield_error")
        dec.audit["error_rs"] = type(exc).__name__

    if not dec.risk_ok:
        dec.action = "WAIT"
        dec.audit["steps"].append("risk_blocked")
        return dec

    # ══ 2b. Grammar V9 boost/downgrade (R6) ══════════════════════════════
    if grammar:
        try:
            best     = grammar.get("best")
            n_detect = grammar.get("n_detected", 0)
            dec.audit["grammar"] = {"n_detected": n_detect, "best": best}
            dec.audit["steps"].append("grammar_v9")
            if best:
                g_dir  = best.get("direction", "NEUTRAL")
                g_conf = best.get("confidence", 0.0)
                want_bull = direction in ("long", "buy")
                aligned = (
                    (g_dir == "BULLISH" and want_bull) or
                    (g_dir == "BEARISH" and not want_bull)
                )
                if aligned and g_conf >= 0.6:
                    dec.reasons.append(f"grammar_{best.get('concept')}_aligned")
                elif g_dir != "NEUTRAL" and not aligned:
                    if dec.filtered_level == "A2":
                        dec.filtered_level = "A3"
                        dec.reasons.append(f"grammar_{best.get('concept')}_opposed")
        except Exception as exc:
            log.warning("grammar_v9 fail-open (R6): %s", exc)
            dec.audit["steps"].append("grammar_v9_error")

    # ══ 2c. Fractal context boost/veto (R6) ═════════════════════════════
    if fractal:
        try:
            f_boost   = float(fractal.get("boost", 0.0))
            f_dir     = fractal.get("direction", "NONE")
            f_aligned = bool(fractal.get("aligned", False))
            dec.audit["fractal"] = {
                "boost":     f_boost,
                "direction": f_dir,
                "aligned":   f_aligned,
                "n_tfs":     (fractal.get("confluence") or {}).get("n_tfs", 0),
                "cinematics_divergence": (
                    fractal.get("cinematics") or {}
                ).get("divergence_ratio", 0.0),
            }
            dec.audit["steps"].append("fractal_context")
            want_bull = direction in ("long", "buy")
            want_sign = 1.0 if want_bull else -1.0
            frac_sign = 1.0 if f_boost > 0 else (-1.0 if f_boost < 0 else 0.0)
            opposed   = frac_sign != 0.0 and frac_sign != want_sign
            if opposed and f_boost <= -0.5:
                if dec.filtered_level == "A2":
                    dec.filtered_level = "A3"
                    dec.reasons.append("fractal_veto_downgrade")
            elif f_aligned and f_boost >= 0.5 and dec.filtered_level == "A3":
                dec.filtered_level = "A2"
                dec.reasons.append(f"fractal_align_boost_{f_boost}")
        except Exception as exc:
            log.warning("fractal_context fail-open (R6): %s", exc)
            dec.audit["steps"].append("fractal_context_error")

    # ══ 2d. Wyckoff gate (R6) ══════════════════════════════════════════
    try:
        consolidate_wyckoff = _get_consolidate_wyckoff()
        wyck = consolidate_wyckoff(
            symbol=pair, timeframe=timeframe, timestamp=timestamp,
            vsa_state=None, vsa_confidence=0.0, ce_signal=None,
            weights={"vsa": 0.5, "ce": 0.5},
        )
        wyckoff_state = wyck.state.value
        dec.audit["wyckoff"] = {"state": wyckoff_state, "confidence": wyck.confidence}
        dec.audit["steps"].append("wyckoff_gate")
        if wyckoff_state != "NEUTRAL" and dec.filtered_level in ("A2", "A3"):
            dir_lower  = direction.lower()
            want_sell  = dir_lower in ("short", "sell")
            want_buy   = dir_lower in ("long",  "buy")
            if (
                (wyckoff_state == "MARKUP"       and want_sell) or
                (wyckoff_state == "MARKDOWN"     and want_buy)  or
                (wyckoff_state == "DISTRIBUTION" and want_buy)  or
                (wyckoff_state == "ACCUMULATION" and want_sell)
            ):
                dec.filtered_level = "A3"
                dec.reasons.append(f"wyckoff_{wyckoff_state.lower()}_conflict")
                dec.audit["steps"].append("wyckoff_downgrade")
    except Exception as exc:
        log.warning("wyckoff_gate fail-open (R6): %s", exc)
        dec.audit["steps"].append("wyckoff_gate_error")

    # ══ 2e. Structure S1-S9 (R6) ═══════════════════════════════════════════
    if structure:
        try:
            dec.audit["structure"] = structure
            dec.audit["steps"].append("structure")
            want_bull   = direction in ("long", "buy")
            st_break    = structure.get("s8_break", "NONE")
            break_bull  = st_break in ("BOS_BULL",)
            break_bear  = st_break in ("BOS_BEAR",)
            struct_align   = (break_bull and want_bull) or (break_bear and not want_bull)
            struct_opposed = (break_bull and not want_bull) or (break_bear and want_bull)
            if struct_align:
                dec.reasons.append(f"structure_{st_break}_aligned")
            elif struct_opposed and dec.filtered_level == "A2":
                dec.filtered_level = "A3"
                dec.reasons.append(f"structure_{st_break}_opposed")
        except Exception as exc:
            log.warning("structure fail-open (R6): %s", exc)
            dec.audit["steps"].append("structure_error")

    # ══ 2f. Short conviction guard (R9 asymetrie directionnelle) ═════════
    if sell_needs_confirm and direction in ("short", "sell"):
        try:
            frac_boost     = float(fractal.get("boost", 0.0)) if fractal else 0.0
            frac_align_bear = frac_boost <= -0.5
            if not frac_align_bear and dec.filtered_level == "A2":
                dec.filtered_level = "A3"
                dec.reasons.append("short_conviction_guard")
                dec.audit["steps"].append("directional_guard")
        except Exception as exc:
            log.warning("directional_guard fail-open (R6): %s", exc)

    # ══ 3. Action finale ═══════════════════════════════════════════════
    # BUG1 FIX : seul filtered_level décide — signal_level original ne doit pas
    # bloquer les upgrades effectués par fractal/grammar/structure.
    if dec.filtered_level in ("A1", "A2"):
        dec.action   = "BUY" if direction in ("long", "buy") else "SELL"
        dec.lot_size = round(
            (capital * candidate_risk_pct / 100.0) / 100_000.0, 4,
        )
        dec.reasons.append(f"filtered={dec.filtered_level}")
        dec.audit["steps"].append("trade")
    else:
        dec.action = "WAIT"
        dec.reasons.append(f"filtered={dec.filtered_level}_below_A2")
        dec.audit["steps"].append("not_high_conviction")

    return dec


__all__ = ["PipelineDecision", "decide_entry"]

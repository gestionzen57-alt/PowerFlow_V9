"""V10 Decision Pipeline — CYCLE 9 MAX PERF (09/08/2026).

Hérite des 3 bugs racine corrigés en C6 :
  BUG1 — filtered_level seul décide l'action finale (pas signal_level)
  BUG2 — fail-open vrai dans compose_filters (continue au lieu de return)
  BUG3 — indentation normalisée au bloc risk_shield

Nouveau C9 :
  DP-C9-OPT1 — session pass-through dans decide_entry()
    session="LONDON"|"NY"|"TOKYO"|"OVERLAP"|"OFF"
    Passé à compose_filters pour filtrage horaire fin.

  DP-C9-OPT2 — rl_score gate sur signal A3
    Si rl_score >= RL_A3_PASS (0.55) ET filtered_level=A3 → upgrade A2
    Même logique que replay_engine C9 OPT4 mais dans le DP lui-même.

  DP-C9-OPT3 — A1 force-trade
    Si filtered_level=A1 ET risk_ok → trade garanti (pas de downgrade grammar/fractal)
    Seul wyckoff fort (MARKDOWN/MARKUP) peut encore veto.

  DP-C9-OPT4 — short_conviction_guard configurable
    Seuil fractal_align_bear abaissé de -0.50 à -0.35 (moins restrictif)
    Évitait des SELL légitimes sur fractal boost modéré (-0.40).

  DP-C9-OPT5 — lot_size ATR-aware (param atr_pip optionnel)
    Si atr_pip fourni : lot = capital * risk_pct / (atr_pip * 10)
    Sinon : lot = capital * risk_pct / 100_000 (fallback C6)

Doctrine : R2 additif, R6 fail-open, R9 audit, R10 compute-only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# DP-C9-OPT2 : seuil RL pour upgrade A3→A2
RL_A3_PASS = 0.55
# DP-C9-OPT4 : seuil fractal bear pour short guard (C6=−0.50, C9=−0.35)
SHORT_GUARD_FRACTAL_THRESH = -0.35

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
    # C9 nouveaux params
    rl_score: float = 0.0,
    atr_pip: Optional[float] = None,
) -> PipelineDecision:
    """Produit la décision finale C9.

    Pipeline :
      1. compose_filters  → filtered_level
      2. risk_shield      → risk_ok
      2a. RL upgrade A3→A2 (DP-C9-OPT2)
      2b. grammar / fractal / wyckoff / structure gates
      2c. A1 force-trade (DP-C9-OPT3)
      3. Action finale + lot ATR-aware (DP-C9-OPT5)

    R6 fail-open : exceptions → pipeline continue avec valeur conservative.
    """
    dec = PipelineDecision(
        pair=pair, timeframe=timeframe, timestamp=timestamp,
        signal_level=signal_level,
    )
    dec.audit = {"steps": [], "c9_rl_score": round(rl_score, 4), "c9_session": session or "UNKNOWN"}

    # ══ 1. Filtres publics ═══════════════════════════════════════════════
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
        log.warning("compose_filters fail-open (R6): %s", exc)
        dec.filtered_level = signal_level
        dec.audit["steps"].append("filter_compositor_error")
        dec.audit["error_fc"] = type(exc).__name__
        # BUG2 hérité C6 : NE PAS return ici

    if dec.filtered_level == "NONE":
        dec.action = "NONE"
        dec.reasons.append("filtered_NONE")
        dec.audit["steps"].append("no_trade")
        return dec

    # ══ 2. Bouclier R10 ═══════════════════════════════════════════════════
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
        log.warning("risk_shield fail-open (R6): %s", exc)
        dec.risk_ok = True
        dec.audit["steps"].append("risk_shield_error")
        dec.audit["error_rs"] = type(exc).__name__

    if not dec.risk_ok:
        dec.action = "WAIT"
        dec.audit["steps"].append("risk_blocked")
        return dec

    # ══ 2a. RL upgrade A3→A2 (DP-C9-OPT2) ════════════════════════════════
    if dec.filtered_level == "A3" and rl_score >= RL_A3_PASS:
        dec.filtered_level = "A2"
        dec.reasons.append(f"rl_upgrade_A3_to_A2(rl={rl_score:.3f})")
        dec.audit["steps"].append("rl_upgrade")
        log.debug("[DP-C9] RL upgrade A3→A2 %s/%s rl=%.3f", pair, timeframe, rl_score)

    # Flag A1 — court-circuite les downgrades grammar/fractal (DP-C9-OPT3)
    is_a1 = dec.filtered_level == "A1"

    # ══ 2b. Grammar V9 boost/downgrade (R6) ═══════════════════════════════
    if grammar and not is_a1:
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

    # ══ 2c. Fractal context boost/veto (R6) ══════════════════════════════
    if fractal and not is_a1:
        try:
            f_boost   = float(fractal.get("boost", 0.0))
            f_dir     = fractal.get("direction", "NONE")
            f_aligned = bool(fractal.get("aligned", False))
            dec.audit["fractal"] = {
                "boost": f_boost, "direction": f_dir, "aligned": f_aligned,
                "n_tfs": (fractal.get("confluence") or {}).get("n_tfs", 0),
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

    # ══ 2d. Wyckoff gate (R6) — seul gate actif sur A1 ═════════════════════
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
        if wyckoff_state != "NEUTRAL" and dec.filtered_level in ("A1", "A2", "A3"):
            dir_lower  = direction.lower()
            want_sell  = dir_lower in ("short", "sell")
            want_buy   = dir_lower in ("long",  "buy")
            if (
                (wyckoff_state == "MARKUP"       and want_sell) or
                (wyckoff_state == "MARKDOWN"     and want_buy)  or
                (wyckoff_state == "DISTRIBUTION" and want_buy)  or
                (wyckoff_state == "ACCUMULATION" and want_sell)
            ):
                # DP-C9-OPT3 : Wyckoff peut downgrader A1→A2 (jamais HOLD)
                if dec.filtered_level == "A1":
                    dec.filtered_level = "A2"
                    dec.reasons.append(f"wyckoff_{wyckoff_state.lower()}_A1_soft_veto")
                    dec.audit["steps"].append("wyckoff_soft_veto_A1")
                else:
                    dec.filtered_level = "A3"
                    dec.reasons.append(f"wyckoff_{wyckoff_state.lower()}_conflict")
                    dec.audit["steps"].append("wyckoff_downgrade")
    except Exception as exc:
        log.warning("wyckoff_gate fail-open (R6): %s", exc)
        dec.audit["steps"].append("wyckoff_gate_error")

    # ══ 2e. Structure S1-S9 (R6) ═════════════════════════════════════════════
    if structure and not is_a1:
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

    # ══ 2f. Short conviction guard C9 (DP-C9-OPT4 : seuil assoupli -0.35) ════
    if sell_needs_confirm and direction in ("short", "sell") and not is_a1:
        try:
            frac_boost      = float(fractal.get("boost", 0.0)) if fractal else 0.0
            frac_align_bear = frac_boost <= SHORT_GUARD_FRACTAL_THRESH  # C9: -0.35 vs -0.50
            if not frac_align_bear and dec.filtered_level == "A2":
                dec.filtered_level = "A3"
                dec.reasons.append("short_conviction_guard_c9")
                dec.audit["steps"].append("directional_guard_c9")
        except Exception as exc:
            log.warning("directional_guard fail-open (R6): %s", exc)

    # ══ 3. Action finale + lot sizing (DP-C9-OPT5 ATR-aware) ════════════════
    # BUG1 hérité C6 : seul filtered_level décide
    if dec.filtered_level in ("A1", "A2"):
        dec.action = "BUY" if direction in ("long", "buy") else "SELL"
        # DP-C9-OPT5 : lot ATR-aware
        if atr_pip is not None and atr_pip > 0:
            dec.lot_size = round(
                (capital * candidate_risk_pct / 100.0) / (atr_pip * 10.0), 4
            )
        else:
            dec.lot_size = round(
                (capital * candidate_risk_pct / 100.0) / 100_000.0, 4,
            )
        dec.reasons.append(f"filtered={dec.filtered_level}")
        dec.audit["steps"].append("trade")
        dec.audit["c9_atr_pip"] = atr_pip
    else:
        dec.action = "WAIT"
        dec.reasons.append(f"filtered={dec.filtered_level}_below_A2")
        dec.audit["steps"].append("not_high_conviction")

    return dec


__all__ = ["PipelineDecision", "decide_entry"]

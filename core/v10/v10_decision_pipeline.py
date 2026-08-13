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


# Z9 : bonus/malus VSA multi-TF appliqué au ctx_score (H8 quality gate)
VSA_ALIGN_BONUS = 0.05
VSA_OPPOSE_MALUS = -0.03


def load_vsa_signal(
    *,
    pair: str,
    timeframe: str,
    db_path: Optional[str] = None,
    vsa_report: Optional[Dict] = None,
) -> Dict:
    """Charge le signal VSA multi-TF (Z9, R2 additif / R6 fail-open).

    Sources, dans l'ordre :
      1. `vsa_report` pré-calculé par l'appelant (replay engine) — évite
         un accès DB par décision.
      2. `db_path` fourni → `load_multi_tf_from_db` + `compute_vsa_signal`
         (lecture des colonnes compression_extension_etat/intensite).
      3. Sinon → état vide {signal: NEUTRAL, ok: False} (R6 : le pipeline
         continue sans bonus ni malus).

    Returns dict {signal, score_global, ok, error, audit} — JSON-safe (R9).
    """
    out = {
        "signal": "NEUTRAL",
        "score_global": 0.0,
        "ok": False,
        "error": None,
        "audit": {"source": "none"},
    }
    if vsa_report is not None and isinstance(vsa_report, dict):
        out["signal"] = str(vsa_report.get("signal") or "NEUTRAL")
        out["score_global"] = float(vsa_report.get("score_global") or 0.0)
        out["ok"] = out["signal"] in ("BULLISH", "BEARISH")
        out["audit"] = {"source": "caller", **dict(vsa_report.get("audit") or {})}
        return out
    if not db_path:
        return out
    try:
        from .v10_compression_extension import (
            compute_vsa_signal,
            load_multi_tf_from_db,
        )
        tfs = ("M30", "H1", "H4") if timeframe in ("M1", "M5", "M15", "M30") \
            else (timeframe,)
        snapshots = load_multi_tf_from_db(db_path, pair, tfs=tfs)
        if not any(snapshots.get(tf) for tf in snapshots):
            out["error"] = "no_snapshots"
            return out
        m30 = snapshots.get("M30", [])
        h1 = snapshots.get("H1", [])
        h4 = snapshots.get("H4", [])
        if not (m30 or h1 or h4):
            out["error"] = "no_data"
            return out
        report = compute_vsa_signal(
            m30, h1, h4, pair, timestamp=out["audit"].get("timestamp", ""),
        )
        out["signal"] = str(getattr(report, "signal", "NEUTRAL") or "NEUTRAL")
        out["score_global"] = float(getattr(report, "score_global", 0.0) or 0.0)
        out["ok"] = out["signal"] in ("BULLISH", "BEARISH")
        out["audit"] = {
            "source": "db",
            "timeframes": list(tfs),
            "n_m30": len(m30), "n_h1": len(h1), "n_h4": len(h4),
            "score_global": out["score_global"],
        }
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


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
    # Z9 : VSA multi-TF (compression_extension) — alignement bonus/malus
    vsa_multi_tf_ok: Optional[bool] = None

    def as_dict(self) -> Dict:
        return {
            "pair": self.pair, "timeframe": self.timeframe,
            "timestamp": self.timestamp, "signal_level": self.signal_level,
            "filtered_level": self.filtered_level, "risk_ok": self.risk_ok,
            "action": self.action, "lot_size": round(self.lot_size, 4),
            "reasons": self.reasons, "audit": dict(self.audit),
            "vsa_multi_tf_ok": self.vsa_multi_tf_ok,
        }


def _session_label(session) -> str:
    """Sérialise `session` en string JSON-safe (R6/R9). `session` peut être un
    objet SessionQuality (non JSON-sérialisable) ou une string. Retourne
    toujours une string."""
    if session is None:
        return "UNKNOWN"
    if isinstance(session, str):
        return session or "UNKNOWN"
    # objet SessionQuality → extraire champs utiles
    try:
        name = getattr(session, "name", None) or getattr(session, "label", None)
        q = getattr(session, "quality_score", None)
        if name is not None:
            return f"{name}(q={q:.2f})" if isinstance(q, (int, float)) else str(name)
        if q is not None:
            return f"session(q={q:.2f})" if isinstance(q, (int, float)) else str(q)
    except Exception:
        pass
    return str(session)


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
    # Z9 : signal VSA multi-TF pré-calculé (compression_extension)
    vsa_report: Optional[Dict] = None,
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
    dec.audit = {"steps": [], "c9_rl_score": round(rl_score, 4), "c9_session": _session_label(session)}

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

    # ══ 2b. Garde-fous institutionnels (C12/C13 — branchés 13/08) ═══════════
    # Circuit breaker DD (R10) + News guard + Correlation guard. Tous R6
    # fail-open : une erreur ne bloque jamais le pipeline, elle laisse passer.
    # Ces modules existaient mais n'étaient branchés que dans les cycle
    # optimizers (zones mortes) — désormais actifs dans le chemin live.
    try:
        from .v10_drawdown_circuit_breaker import check_circuit_breaker
        cb = check_circuit_breaker(daily_dd=daily_dd_pct / 100.0)
        dec.audit["circuit_breaker"] = cb.as_dict()
        dec.audit["steps"].append("circuit_breaker")
        if cb.halt_trading:
            dec.risk_ok = False
            dec.reasons.append(f"circuit_breaker_{cb.level}:{cb.trigger}")
    except Exception as exc:
        log.warning("circuit_breaker fail-open (R6): %s", exc)
        dec.audit["steps"].append("circuit_breaker_error")

    try:
        from .v10_news_guard import check_news_window
        from datetime import datetime as _dt
        _ts = timestamp.replace("Z", "+00:00") if timestamp else ""
        _t = _dt.fromisoformat(_ts) if _ts else _dt.now()
        ng = check_news_window(_t, pair=pair)
        dec.audit["news_guard"] = ng.as_dict()
        dec.audit["steps"].append("news_guard")
        if not ng.allowed:
            dec.risk_ok = False
            dec.reasons.append(f"news_guard_blocked:{ng.blocked_by}")
    except Exception as exc:
        log.warning("news_guard fail-open (R6): %s", exc)
        dec.audit["steps"].append("news_guard_error")

    try:
        from .v10_correlation_guard import check_correlation
        _open = {p.get("symbol", p.get("pair", "?")): float(p.get("lots", p.get("lot_size", 0.0)) or 0.0)
                 for p in (positions or [])}
        cg = check_correlation(pair, dec.lot_size or 0.01, _open)
        dec.audit["correlation_guard"] = cg.as_dict()
        dec.audit["steps"].append("correlation_guard")
        if not cg.allowed:
            dec.risk_ok = False
            dec.reasons.append(f"correlation_blocked:{cg.block_reason}")
    except Exception as exc:
        log.warning("correlation_guard fail-open (R6): %s", exc)
        dec.audit["steps"].append("correlation_guard_error")

    if not dec.risk_ok:
        dec.action = "WAIT"
        dec.audit["steps"].append("institutional_guards_blocked")
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

    # ══ 2g. VSA multi-TF (Z9 — compression_extension, H8 quality gate) ════
    # Bonus +0.05 si VSA aligné avec la direction, malus -0.03 sinon.
    # R6 fail-open : échec de chargement → aucun impact, vsa_multi_tf_ok=None.
    try:
        vsa = load_vsa_signal(
            pair=pair, timeframe=timeframe, vsa_report=vsa_report,
        )
        dec.audit["vsa_multi_tf"] = vsa
        dec.audit["steps"].append("vsa_multi_tf")
        if vsa["ok"]:
            want_bull = direction in ("long", "buy")
            vsa_bull = vsa["signal"] == "BULLISH"
            if vsa_bull == want_bull:
                dec.vsa_multi_tf_ok = True
                dec.reasons.append("vsa_multi_tf_aligned_bonus")
                dec.audit["steps"].append("vsa_bonus")
            else:
                dec.vsa_multi_tf_ok = False
                dec.reasons.append("vsa_multi_tf_opposed_malus")
                dec.audit["steps"].append("vsa_malus")
        else:
            dec.vsa_multi_tf_ok = None
            dec.reasons.append(f"vsa_multi_tf_unavailable_{vsa['error'] or 'no_signal'}")
    except Exception as exc:
        log.warning("vsa_multi_tf fail-open (R6): %s", exc)
        dec.vsa_multi_tf_ok = None
        dec.audit["steps"].append("vsa_multi_tf_error")

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


__all__ = ["PipelineDecision", "decide_entry", "load_vsa_signal", "VSA_ALIGN_BONUS", "VSA_OPPOSE_MALUS"]

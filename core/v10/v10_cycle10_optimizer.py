"""
V10 Cycle 10 Optimizer — CYCLE 10 (09/08/2026)

Module additif (R2) qui post-traite les résultats du ReplayEngine C9-FINAL
pour implémenter la boucle d'apprentissage C10 :

  C10-OPT1 — WalkForward outcomes → BayesianRecalibrator.update()
  C10-OPT2 — MetaOptimizer hook si global_wr < TARGET_WR
  C10-OPT3 — RL Promotion gate
  C10-OPT4 — LiveGate switch (compute-only, R10)
  C10-OPT5 — Baselines C9-FINAL
  C10-OPT6 — Cycle tag "10"

Doctrine :
  R2  — additif pur : zéro import core/v9/
  R6  — fail-open  : toute exception → warn + continue
  R9  — audit      : chaque action tracée dans le rapport
  R10 — compute-only : zéro ordre réel, zéro écriture MT5/IBKR
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ══ SEUILS C10 ═══════════════════════════════════════════════════════

TARGET_WR          = 0.45   # C10-OPT2 : déclenche MetaOpt si global_wr < seuil
LIVE_GATE_WR       = 0.48   # C10-OPT4 : live_ready si WR >= seuil
LIVE_GATE_PNL      = 0.0    # C10-OPT4 : live_ready si PnL >= seuil
RL_PROMOTE_THRESH  = 0.70   # C10-OPT3 : promeut configs rl_score >= seuil
RL_PROMOTE_MIN_TRADES = 20  # C10-OPT3 : gate n_trades minimum
RL_PROMOTE_MIN_WR     = 0.40  # C10-OPT3 : gate WR minimum

# Baselines C9-FINAL (C10-OPT5) — mis à jour après chaque run C9
_C9_WR  = 0.0
_C9_PNL = 0.0


# ══ IMPORTS fail-open (R6) ═══════════════════════════════════════════

try:
    from .v10_bayesian_recalibrator import BayesianRecalibrator
    _BAYES_CLS_OK = True
except Exception as _e:
    log.warning("[C10] BayesianRecalibrator KO: %s", _e)
    BayesianRecalibrator = None
    _BAYES_CLS_OK = False

try:
    from .v10_meta_optimizer import MetaOptimizer
    _META_OK = True
except Exception as _e:
    log.warning("[C10] MetaOptimizer KO: %s", _e)
    MetaOptimizer = None
    _META_OK = False

try:
    from .v10_rl_promotion import RLPromotion
    _RL_PROMO_OK = True
except Exception as _e:
    log.warning("[C10] RLPromotion KO: %s", _e)
    RLPromotion = None
    _RL_PROMO_OK = False


# ══ DATACLASS RÉSULTAT C10 ════════════════════════════════════════════

@dataclass
class C10PostprocessResult:
    """Résultat du post-traitement C10 après run_all()."""
    global_wr:               float = 0.0
    global_pnl:              float = 0.0
    bayes_updated:           int   = 0    # nombre de priors mis à jour
    meta_opt_triggered:      bool  = False
    meta_opt_result:         Dict  = field(default_factory=dict)
    rl_promoted:             int   = 0    # nombre de configs promues
    live_ready:              bool  = False
    live_ready_reason:       str   = ""
    walk_forward_outcomes:   int   = 0    # total outcomes traités
    wr_delta_vs_c9:          float = 0.0
    pnl_delta_vs_c9:         float = 0.0
    audit:                   Dict  = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "global_wr":             self.global_wr,
            "global_pnl":            self.global_pnl,
            "bayes_updated":         self.bayes_updated,
            "meta_opt_triggered":    self.meta_opt_triggered,
            "meta_opt_result":       self.meta_opt_result,
            "rl_promoted":           self.rl_promoted,
            "live_ready":            self.live_ready,
            "live_ready_reason":     self.live_ready_reason,
            "walk_forward_outcomes": self.walk_forward_outcomes,
            "wr_delta_vs_c9":        self.wr_delta_vs_c9,
            "pnl_delta_vs_c9":       self.pnl_delta_vs_c9,
            "audit":                 self.audit,
        }


# ══ C10-OPT1 : WalkForward → BayesUpdate ════════════════════════════

def _collect_outcomes_from_report(report_dict: Dict) -> List[Dict]:
    """
    Extrait les outcomes (win/loss) depuis le rapport ReplayEngine.
    Retourne une liste de dicts {pair, tf, signal_level, reward}.
    """
    outcomes: List[Dict] = []
    try:
        for row in report_dict.get("by_pair_tf", []):
            pair = row.get("pair", "")
            tf   = row.get("tf", "")
            for dec in row.get("decisions", []):
                if dec.get("action") not in ("BUY", "SELL"):
                    continue
                pnl    = float(dec.get("pnl_pips", 0.0) or 0.0)
                sl     = dec.get("signal_level", "A3")
                reward = 1.0 if pnl > 0 else 0.0
                outcomes.append({
                    "pair":         pair,
                    "tf":           tf,
                    "signal_level": sl,
                    "reward":       reward,
                    "pnl":          pnl,
                })
    except Exception as exc:
        log.warning("[C10-OPT1] collect_outcomes fail-open: %s", exc)
    return outcomes


def _update_bayesian_priors(
    outcomes: List[Dict],
    db_path: str,
) -> int:
    """
    C10-OPT1 : alimente BayesianRecalibrator.update() pour chaque outcome.
    Retourne le nombre de priors mis à jour.
    Fail-open R6.
    """
    if not _BAYES_CLS_OK or BayesianRecalibrator is None:
        return 0
    updated = 0
    # Regrouper par (pair, tf) pour instancier 1 recalibrator par paire×TF
    from collections import defaultdict
    by_pair_tf: Dict[tuple, List[Dict]] = defaultdict(list)
    for o in outcomes:
        by_pair_tf[(o["pair"], o["tf"])].append(o)

    for (pair, tf), ocs in by_pair_tf.items():
        try:
            recal = BayesianRecalibrator(db_path=db_path, symbol=pair, timeframe=tf)
            for o in ocs:
                try:
                    recal.update(
                        signal_level=o.get("signal_level", "A3"),
                        reward=o["reward"],
                    )
                    updated += 1
                except Exception as exc_upd:
                    log.debug("[C10-BAYES] update fail-open %s/%s: %s", pair, tf, exc_upd)
        except Exception as exc_init:
            log.warning("[C10-BAYES] init fail-open %s/%s: %s", pair, tf, exc_init)
    log.info("[C10-OPT1] BayesUpdate : %d priors mis à jour", updated)
    return updated


# ══ C10-OPT2 : MetaOptimizer hook ═══════════════════════════════════

def _run_meta_optimizer_if_needed(
    global_wr: float,
    db_path: str,
) -> Dict:
    """
    C10-OPT2 : déclenche MetaOptimizer si global_wr < TARGET_WR.
    Retourne le résultat ou {} si non déclenché / fail-open.
    """
    if global_wr >= TARGET_WR:
        log.info("[C10-OPT2] MetaOpt skip — WR=%.3f >= TARGET=%.3f", global_wr, TARGET_WR)
        return {"skipped": True, "reason": f"wr={global_wr:.3f}_above_target={TARGET_WR}"}
    if not _META_OK or MetaOptimizer is None:
        log.warning("[C10-OPT2] MetaOptimizer KO — skip")
        return {"skipped": True, "reason": "meta_optimizer_import_failed"}
    try:
        meta = MetaOptimizer(db_path=db_path)
        result = meta.run_cycle()
        out = result.as_dict() if hasattr(result, "as_dict") else (result if isinstance(result, dict) else {})
        log.info("[C10-OPT2] MetaOpt triggered — result keys: %s", list(out.keys()))
        return out
    except Exception as exc:
        log.warning("[C10-OPT2] MetaOpt fail-open: %s", exc)
        return {"error": str(exc), "fail_open": True}


# ══ C10-OPT3 : RL Promotion gate ════════════════════════════════════

def _run_rl_promotion(
    report_dict: Dict,
    db_path: str,
) -> int:
    """
    C10-OPT3 : promeut les configs rl_score >= RL_PROMOTE_THRESH
    si n_trades >= RL_PROMOTE_MIN_TRADES ET wr >= RL_PROMOTE_MIN_WR.
    Retourne le nombre de configs promues.
    Fail-open R6.
    """
    if not _RL_PROMO_OK or RLPromotion is None:
        log.warning("[C10-OPT3] RLPromotion KO — skip")
        return 0
    promoted = 0
    try:
        promo = RLPromotion(db_path=db_path)
        for row in report_dict.get("by_pair_tf", []):
            pair     = row.get("pair", "")
            tf       = row.get("tf", "")
            n_trades = row.get("n_trades", 0)
            wr       = float(row.get("wr", 0.0) or 0.0)
            if n_trades < RL_PROMOTE_MIN_TRADES or wr < RL_PROMOTE_MIN_WR:
                continue
            decisions = row.get("decisions", [])
            high_rl = [
                d for d in decisions
                if float(d.get("rl_score", 0.0) or 0.0) >= RL_PROMOTE_THRESH
                and d.get("action") in ("BUY", "SELL")
            ]
            if not high_rl:
                continue
            try:
                avg_rl = sum(float(d.get("rl_score", 0.0) or 0.0) for d in high_rl) / len(high_rl)
                promo.promote(
                    symbol=pair,
                    timeframe=tf,
                    rl_score=avg_rl,
                    wr=wr,
                    n_trades=n_trades,
                )
                promoted += 1
                log.info("[C10-OPT3] RL promoted %s/%s rl=%.3f wr=%.3f n=%d",
                         pair, tf, avg_rl, wr, n_trades)
            except Exception as exc_p:
                log.debug("[C10-OPT3] promote fail-open %s/%s: %s", pair, tf, exc_p)
    except Exception as exc:
        log.warning("[C10-OPT3] rl_promotion fail-open: %s", exc)
    log.info("[C10-OPT3] RL Promotion : %d configs promues", promoted)
    return promoted


# ══ C10-OPT4 : LiveGate ══════════════════════════════════════════════

def _evaluate_live_gate(global_wr: float, global_pnl: float) -> tuple:
    """
    C10-OPT4 : évalue si les conditions live sont atteintes.
    Compute-only (R10) — zéro ordre réel.
    Retourne (live_ready: bool, reason: str).
    """
    if global_wr >= LIVE_GATE_WR and global_pnl >= LIVE_GATE_PNL:
        reason = (
            f"WR={global_wr:.3f}>={LIVE_GATE_WR} "
            f"ET PnL={global_pnl:.0f}>={LIVE_GATE_PNL} — LIVE_GATE_OPEN"
        )
        log.info("[C10-OPT4] LIVE_GATE OPEN — %s", reason)
        return True, reason
    parts = []
    if global_wr  < LIVE_GATE_WR:  parts.append(f"WR={global_wr:.3f}<{LIVE_GATE_WR}")
    if global_pnl < LIVE_GATE_PNL: parts.append(f"PnL={global_pnl:.0f}<{LIVE_GATE_PNL}")
    reason = "LIVE_GATE_CLOSED — " + ", ".join(parts)
    log.info("[C10-OPT4] %s", reason)
    return False, reason


# ══ POINT D'ENTRÉE PRINCIPAL ═════════════════════════════════════════

def run_cycle10_postprocess(
    report_dict: Dict,
    db_path: str = "data/powerflow.db",
) -> C10PostprocessResult:
    """
    Post-traitement C10 complet après ReplayEngine.run_all().

    Enchaîne :
      1. C10-OPT1 : collect outcomes → BayesUpdate
      2. C10-OPT2 : MetaOpt si WR < TARGET
      3. C10-OPT3 : RL Promotion gate
      4. C10-OPT4 : LiveGate evaluation

    Fail-open R6 — ne lève jamais vers le caller.
    """
    result = C10PostprocessResult()
    try:
        global_wr  = float(report_dict.get("global_wr", 0.0) or 0.0)
        global_pnl = float(report_dict.get("global_pnl_pips", 0.0) or 0.0)
        result.global_wr  = global_wr
        result.global_pnl = global_pnl

        # C10-OPT5 : deltas vs C9-FINAL
        result.wr_delta_vs_c9  = round(global_wr  - _C9_WR,  4)
        result.pnl_delta_vs_c9 = round(global_pnl - _C9_PNL, 2)

        # C10-OPT1 : WalkForward → BayesUpdate
        outcomes = _collect_outcomes_from_report(report_dict)
        result.walk_forward_outcomes = len(outcomes)
        result.bayes_updated = _update_bayesian_priors(outcomes, db_path)

        # C10-OPT2 : MetaOpt hook
        meta_result = _run_meta_optimizer_if_needed(global_wr, db_path)
        result.meta_opt_triggered = not meta_result.get("skipped", False)
        result.meta_opt_result    = meta_result

        # C10-OPT3 : RL Promotion
        result.rl_promoted = _run_rl_promotion(report_dict, db_path)

        # C10-OPT4 : LiveGate
        result.live_ready, result.live_ready_reason = _evaluate_live_gate(global_wr, global_pnl)

        result.audit = {
            "cycle":               "10",
            "c10_features": [
                "walk_forward_bayes_update",
                "meta_optimizer_hook",
                "rl_promotion_gate",
                "live_gate_compute_only",
                "c9_baseline_delta",
                "cycle_tag_10",
            ],
            "thresholds": {
                "target_wr":           TARGET_WR,
                "live_gate_wr":        LIVE_GATE_WR,
                "live_gate_pnl":       LIVE_GATE_PNL,
                "rl_promote_thresh":   RL_PROMOTE_THRESH,
                "rl_promote_min_trades": RL_PROMOTE_MIN_TRADES,
                "rl_promote_min_wr":   RL_PROMOTE_MIN_WR,
            },
            "modules": {
                "bayes_recalibrator": _BAYES_CLS_OK,
                "meta_optimizer":     _META_OK,
                "rl_promotion":       _RL_PROMO_OK,
            },
        }

        log.info(
            "[C10-FINAL] WR=%.1f%%(ΔC9=%+.1f%%) PnL=%.0f bayes=%d "
            "meta=%s rl_promo=%d live=%s",
            global_wr * 100, result.wr_delta_vs_c9 * 100,
            global_pnl,
            result.bayes_updated,
            "ON" if result.meta_opt_triggered else "OFF",
            result.rl_promoted,
            "OPEN" if result.live_ready else "CLOSED",
        )

    except Exception as exc:
        log.warning("[C10] run_cycle10_postprocess fail-open (R6): %s", exc)
        result.audit["error"] = str(exc)

    return result


__all__ = [
    "C10PostprocessResult",
    "run_cycle10_postprocess",
    "TARGET_WR", "LIVE_GATE_WR", "LIVE_GATE_PNL",
    "RL_PROMOTE_THRESH", "RL_PROMOTE_MIN_TRADES", "RL_PROMOTE_MIN_WR",
    "_C9_WR", "_C9_PNL",
]

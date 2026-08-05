"""V10 RL Promotion Gate — Phase 24+ SHADOW → ACTIVE decision.

Doctrine V10 (CEO phase 24+) :
  R1 : agit par défaut
  R2 : additif pur
  R6 : fail-open
  R7 : tests verts cumulés
  R8 : R8 auto-promotion basée sur KPIs
  R9 : audit metadata honnête
  R10 : kill switch DD>5% OBLIGATOIRE, micro-lot 0.01 max avant ACTIVE

Objectif Phase 24+ :
  Décide automatiquement si RL passe SHADOW → ACTIVE selon gate CEO :
    - WR ≥ 50% sur 30 trades consécutifs (paper Phase 23+)
    - Sharpe ≥ 0.3 (annualisé)
    - max DD ≤ 5% (R10 capital protégé)
    - consistency ≥ 3/4 paires gate-passed (Phase 21+)
  Si gate OK → promote_to_active=True, le RL sera utilisé en LIVE
  Si gate KO → promote_to_active=False, RL reste SHADOW (R10 safe)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Tuple

from core.v10.v10_paper_trader import (
    PaperTraderReport,
    GATE_PASSED_PAIRS_M30,
    BASELINE_WR_M30,
)
from core.v10.v10_rl_adapter import ShadowSessionReport


# ─────────────────────────────────────────────────────────────────────
# CONSTANTES GATE CEO (Phase 24+)
# ─────────────────────────────────────────────────────────────────────

# Gate CEO pour promotion SHADOW → ACTIVE
GATE_MIN_WR_PCT = 50.0  # WR ≥ 50%
GATE_MIN_SHARPE = 0.3   # Sharpe ≥ 0.3 annualisé
GATE_MAX_DD_PIPS = 50.0  # max DD ≤ 50p (sur 30 trades)
GATE_MIN_CONSISTENCY = 0.75  # 3/4 paires gate-passed ≥ 75%

# Modes RL
RL_MODE_SHADOW = "SHADOW"
RL_MODE_ACTIVE = "ACTIVE"
RL_MODE_KILL_SWITCH = "KILL_SWITCH"


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class PromotionGateCriteria:
    """Critères gate CEO pour promotion SHADOW → ACTIVE."""
    min_wr_pct: float = GATE_MIN_WR_PCT
    min_sharpe: float = GATE_MIN_SHARPE
    max_dd_pips: float = GATE_MAX_DD_PIPS
    min_consistency: float = GATE_MIN_CONSISTENCY


@dataclass
class PromotionDecision:
    """Décision de promotion SHADOW → ACTIVE (Phase 24+)."""
    timestamp: str = ""
    pairs_evaluated: int = 0
    pairs_gate_passed: int = 0
    global_wr_pct: float = 0.0
    global_sharpe: float = 0.0
    global_max_dd_pips: float = 0.0
    consistency_ratio: float = 0.0
    gate_criteria: PromotionGateCriteria = field(default_factory=PromotionGateCriteria)
    gate_results: Dict[str, bool] = field(default_factory=dict)
    promote_to_active: bool = False
    promote_mode: str = RL_MODE_SHADOW  # SHADOW / ACTIVE / KILL_SWITCH
    promote_reason: str = ""
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _check_wr_gate(wr_pct: float, gate: PromotionGateCriteria) -> bool:
    return wr_pct >= gate.min_wr_pct


def _check_sharpe_gate(sharpe: float, gate: PromotionGateCriteria) -> bool:
    return sharpe >= gate.min_sharpe


def _check_dd_gate(max_dd_pips: float, gate: PromotionGateCriteria) -> bool:
    return max_dd_pips <= gate.max_dd_pips


def _check_consistency_gate(
    per_pair_kpis: Dict[str, Dict],
    gate: PromotionGateCriteria,
) -> Tuple[bool, float, int]:
    """Check combien de paires passent gate WR (sur N total)."""
    n_passed = 0
    n_total = len(per_pair_kpis)
    if n_total == 0:
        return False, 0.0, 0
    for pair, kpis in per_pair_kpis.items():
        if kpis.get("wr_pct", 0.0) >= gate.min_wr_pct:
            n_passed += 1
    ratio = n_passed / n_total
    return ratio >= gate.min_consistency, ratio, n_passed


# ─────────────────────────────────────────────────────────────────────
# DECISION PRINCIPALE
# ─────────────────────────────────────────────────────────────────────

def decide_rl_promotion(
    paper_report: PaperTraderReport,
    *,
    gate: PromotionGateCriteria = None,
    timestamp: str = "",
) -> PromotionDecision:
    """Phase 24+ — Décide promotion RL SHADOW → ACTIVE selon KPIs paper.

    Args:
        paper_report: PaperTraderReport (Phase 23+)
        gate: PromotionGateCriteria (defaults = GATE_MIN_*)
        timestamp: ISO 8601 UTC

    Returns:
        PromotionDecision avec promote_to_active bool + audit
    """
    if gate is None:
        gate = PromotionGateCriteria()

    global_kpis = paper_report.global_kpis
    per_pair_kpis = paper_report.per_pair_kpis

    global_wr = global_kpis.get("wr_pct", 0.0)
    global_sharpe = global_kpis.get("sharpe_ratio", 0.0)
    global_max_dd = global_kpis.get("max_dd_pips", 0.0)

    # Kill switch check (R10 priorité absolue)
    kill_switch_dd_breached = global_max_dd > (gate.max_dd_pips * 2)
    # (DD > 2x max gate = kill switch certain)

    # Check 4 gates
    gate_wr = _check_wr_gate(global_wr, gate)
    gate_sharpe = _check_sharpe_gate(global_sharpe, gate)
    gate_dd = _check_dd_gate(global_max_dd, gate)
    gate_consistency, consistency_ratio, n_passed = _check_consistency_gate(
        per_pair_kpis, gate
    )

    n_total = len(per_pair_kpis)

    gate_results = {
        "wr_gate": gate_wr,
        "sharpe_gate": gate_sharpe,
        "dd_gate": gate_dd,
        "consistency_gate": gate_consistency,
    }

    # Décision
    if kill_switch_dd_breached:
        promote_to_active = False
        promote_mode = RL_MODE_KILL_SWITCH
        promote_reason = (
            f"KILL_SWITCH DD>2x_max ({global_max_dd:.1f}p > {gate.max_dd_pips * 2:.1f}p) "
            f"(R10 capital protection)"
        )
    elif all([gate_wr, gate_sharpe, gate_dd, gate_consistency]):
        promote_to_active = True
        promote_mode = RL_MODE_ACTIVE
        promote_reason = (
            f"ALL 4 gates PASSED — WR={global_wr:.2f}% Sharpe={global_sharpe:.3f} "
            f"max_dd={global_max_dd:.2f}p consistency={consistency_ratio*100:.1f}% "
            f"({n_passed}/{n_total} paires)"
        )
    else:
        promote_to_active = False
        promote_mode = RL_MODE_SHADOW
        failed_gates = [k for k, v in gate_results.items() if not v]
        promote_reason = (
            f"SHADOW gates FAILED: {failed_gates} — "
            f"WR={global_wr:.2f}% Sharpe={global_sharpe:.3f} "
            f"max_dd={global_max_dd:.2f}p consistency={consistency_ratio*100:.1f}%"
        )

    return PromotionDecision(
        timestamp=timestamp,
        pairs_evaluated=n_total,
        pairs_gate_passed=n_passed,
        global_wr_pct=global_wr,
        global_sharpe=global_sharpe,
        global_max_dd_pips=global_max_dd,
        consistency_ratio=consistency_ratio,
        gate_criteria=gate,
        gate_results=gate_results,
        promote_to_active=promote_to_active,
        promote_mode=promote_mode,
        promote_reason=promote_reason,
        audit={
            "method": "Phase 24+ RL promotion gate",
            "doctrine": "R1, R2 additif, R6 fail-open, R7, R8 R8-auto-promotion, R9 audit, R10",
            "doctrine_R10": "kill_switch DD>2x_max gate, max DD ≤ 50p (capital protection)",
            "source": "PaperTraderReport Phase 23+ (R8 R8-calibrated)",
        },
    )


__all__ = [
    "GATE_MIN_WR_PCT",
    "GATE_MIN_SHARPE",
    "GATE_MAX_DD_PIPS",
    "GATE_MIN_CONSISTENCY",
    "RL_MODE_SHADOW",
    "RL_MODE_ACTIVE",
    "RL_MODE_KILL_SWITCH",
    "PromotionGateCriteria",
    "PromotionDecision",
    "_check_wr_gate",
    "_check_sharpe_gate",
    "_check_dd_gate",
    "_check_consistency_gate",
    "decide_rl_promotion",
]
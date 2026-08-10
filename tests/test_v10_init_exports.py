"""tests/test_v10_init_exports.py — H-EXPORTS.

Vérifie que les modules V10 prioritaires (audit run_exports_audit.py +
priorité CEO) sont bien exportés depuis core.v10.__init__ (R2 additif).

  - v10_perplexity_sigma_oracle  (priorité absolue)
  - v10_behavior_rag             (priorité absolue)
  - v10_net_exposure             (priorité absolue)
  - v10_rl_promotion             (ADD_TO_INIT par l'audit + priorité absolue)

Doctrine : R2 additif pur, R7 tests verts, R9 audit, R10 compute only.
"""
from __future__ import annotations

import core.v10 as v10

# ─────────────────────────────────────────────────────────────────────
# v10_perplexity_sigma_oracle (priorité absolue)
# ─────────────────────────────────────────────────────────────────────

def test_sigma_oracle_get_sigma_history_exported():
    """get_sigma_history exporté (source sigma pré-vague)."""
    assert hasattr(v10, "get_sigma_history")
    assert callable(v10.get_sigma_history)


# ─────────────────────────────────────────────────────────────────────
# v10_behavior_rag (priorité absolue)
# ─────────────────────────────────────────────────────────────────────

def test_behavior_rag_analogous_behaviors_exported():
    """analogous_behaviors exporté (RAG comportemental)."""
    assert hasattr(v10, "analogous_behaviors")
    assert callable(v10.analogous_behaviors)


def test_behavior_rag_attr_weights_exported():
    """ATTR_WEIGHTS exporté (poids d'attributs RAG)."""
    assert hasattr(v10, "ATTR_WEIGHTS")
    assert isinstance(v10.ATTR_WEIGHTS, dict)


# ─────────────────────────────────────────────────────────────────────
# v10_net_exposure (priorité absolue)
# ─────────────────────────────────────────────────────────────────────

def test_net_exposure_exported():
    """NetExposureResult + ExposureGate exportés."""
    assert hasattr(v10, "NetExposureResult")
    assert hasattr(v10, "ExposureGate")


def test_net_exposure_compute_exported():
    """compute_net_exposure exporté et appelable."""
    assert hasattr(v10, "compute_net_exposure")
    assert callable(v10.compute_net_exposure)


# ─────────────────────────────────────────────────────────────────────
# v10_rl_promotion (ADD_TO_INIT par l'audit)
# ─────────────────────────────────────────────────────────────────────

def test_rl_promotion_dataclasses_exported():
    """PromotionGateCriteria + PromotionDecision exportés (ADD_TO_INIT)."""
    assert hasattr(v10, "PromotionGateCriteria")
    assert hasattr(v10, "PromotionDecision")


def test_rl_promotion_decide_exported():
    """decide_rl_promotion exporté et appelable."""
    assert hasattr(v10, "decide_rl_promotion")
    assert callable(v10.decide_rl_promotion)


def test_rl_promotion_gate_constants_exported():
    """Constantes de gate CEO exportées (R8 auto-promotion)."""
    assert v10.GATE_MIN_WR_PCT == 50.0
    assert v10.GATE_MIN_SHARPE == 0.3
    assert v10.GATE_MAX_DD_PIPS == 50.0
    assert v10.GATE_MIN_CONSISTENCY == 0.75


def test_rl_promotion_modes_exported():
    """Modes RL exportés (SHADOW/ACTIVE/KILL_SWITCH)."""
    assert v10.RL_MODE_SHADOW == "SHADOW"
    assert v10.RL_MODE_ACTIVE == "ACTIVE"
    assert v10.RL_MODE_KILL_SWITCH == "KILL_SWITCH"


# ─────────────────────────────────────────────────────────────────────
# Cohérence R2 : tous les modules prioritaires présents
# ─────────────────────────────────────────────────────────────────────

def test_all_priority_modules_importable():
    """Les 4 modules prioritaires H-EXPORTS sont importables via core.v10."""
    from core.v10.v10_behavior_rag import analogous_behaviors as s2
    from core.v10.v10_net_exposure import compute_net_exposure as s3
    from core.v10.v10_perplexity_sigma_oracle import get_sigma_history as s1
    from core.v10.v10_rl_promotion import decide_rl_promotion as s4
    assert callable(s1) and callable(s2) and callable(s3) and callable(s4)

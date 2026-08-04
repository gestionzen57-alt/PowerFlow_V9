"""V10 RL Adapter — tests unitaires (Phase 4 RL).

Cible R7 : 25 tests verts minimum.

Doctrine V10 :
  R10 : RL kill switch DD > 5%
  Shadow mode par défaut
  Feature vector EXACT 5 dims (CEO spec)
"""
from __future__ import annotations

import json
import math
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict

import pytest

from core.v10.v10_rl_adapter import (
    RLMode,
    FeatureVector,
    BanditArm,
    ShadowTrade,
    RLState,
    ADWINDriftDetector,
    ThompsonBandit,
    RLAdapter,
    BANDIT_ARMS,
    EXPLORATION_EPSILON,
    MAX_DD_PCT_KILL_SWITCH,
    SESSION_QUALITY_BY_TF,
    SHADOW_TABLE_NAME,
)


# ─────────────────────────────────────────────────────────────────────
# 1. DEFAULTS / CONSTANTS
# ─────────────────────────────────────────────────────────────────────

def test_bandit_3_arms():
    assert len(BANDIT_ARMS) == 3
    assert "A1_BOOST" in BANDIT_ARMS
    assert "A1_DAMPEN" in BANDIT_ARMS
    assert "NEUTRAL" in BANDIT_ARMS


def test_epsilon_exploration_10pct():
    """CEO spec : epsilon = 10%."""
    assert EXPLORATION_EPSILON == 0.10


def test_max_dd_kill_switch_5pct():
    """CEO spec : kill switch DD > 5%."""
    assert MAX_DD_PCT_KILL_SWITCH == 5.0


def test_session_quality_all_tf_covered():
    """CEO spec : M15/M30/H1/H4/D1."""
    for tf in ("M15", "M30", "H1", "H4", "D1"):
        assert tf in SESSION_QUALITY_BY_TF
        assert 0.0 <= SESSION_QUALITY_BY_TF[tf] <= 1.0


# ─────────────────────────────────────────────────────────────────────
# 2. FEATURE VECTOR (CEO spec EXACT 5 dims)
# ─────────────────────────────────────────────────────────────────────

def test_feature_vector_default_construction():
    fv = FeatureVector()
    assert fv.context_score == 0.0
    assert fv.phase_score == 0.0
    assert fv.solidarity == 0.0
    assert fv.aligned_count == 0.0
    assert fv.session_quality == 0.0


def test_feature_vector_as_list_5_dims():
    """CEO spec EXACT : 5 dimensions."""
    fv = FeatureVector(context_score=80, phase_score=0.7, solidarity=0.9, aligned_count=3.0, session_quality=0.95)
    lst = fv.as_list()
    assert len(lst) == 5


def test_feature_vector_normalized_to_unit():
    """context_score/100 et aligned_count/4 pour normalisation."""
    fv = FeatureVector(context_score=100, aligned_count=4)
    lst = fv.as_list()
    assert lst[0] == 1.0  # context_score/100
    assert lst[3] == 1.0  # aligned_count/4


def test_build_feature_vector_phase_mapping():
    """phase_score map : REVERSAL=0, EXHAUSTION=0.33, MATURE=0.67, EARLY=1.0."""
    rl = RLAdapter()
    fv_rev = rl.build_feature_vector(50, "REVERSAL", 0.5, 3, "H1")
    fv_exh = rl.build_feature_vector(50, "EXHAUSTION", 0.5, 3, "H1")
    fv_mat = rl.build_feature_vector(50, "MATURE", 0.5, 3, "H1")
    fv_ear = rl.build_feature_vector(50, "EARLY", 0.5, 3, "H1")
    assert fv_rev.phase_score == 0.0
    assert fv_exh.phase_score == 0.33
    assert fv_mat.phase_score == 0.67
    assert fv_ear.phase_score == 1.0


def test_build_feature_vector_session_quality_by_tf():
    """session_quality dépend du TF."""
    rl = RLAdapter()
    fv_m15 = rl.build_feature_vector(50, "MATURE", 0.5, 3, "M15")
    fv_h1 = rl.build_feature_vector(50, "MATURE", 0.5, 3, "H1")
    assert fv_m15.session_quality == SESSION_QUALITY_BY_TF["M15"]
    assert fv_h1.session_quality == SESSION_QUALITY_BY_TF["H1"]


def test_feature_vector_unknown_tf_default():
    rl = RLAdapter()
    fv = rl.build_feature_vector(50, "MATURE", 0.5, 3, "UNKNOWN")
    assert fv.session_quality == 0.5  # default


# ─────────────────────────────────────────────────────────────────────
# 3. BANDIT
# ─────────────────────────────────────────────────────────────────────

def test_bandit_arm_default_priors():
    arm = BanditArm(name="TEST")
    assert arm.alpha == 1.0
    assert arm.beta == 1.0
    assert arm.n_pulls == 0
    assert arm.mean_reward == 0.0


def test_bandit_arm_update_increases_alpha():
    arm = BanditArm(name="TEST")
    arm.update(1.0)  # reward=1
    assert arm.alpha == 2.0  # prior + 1
    assert arm.beta == 1.0
    assert arm.n_pulls == 1


def test_bandit_arm_update_zero_increases_beta():
    arm = BanditArm(name="TEST")
    arm.update(0.0)  # reward=0
    assert arm.alpha == 1.0
    assert arm.beta == 2.0


def test_bandit_arm_update_clip():
    arm = BanditArm(name="TEST")
    arm.update(2.0)  # clip à 1
    assert arm.alpha == 2.0
    arm.update(-1.0)  # clip à 0
    assert arm.beta == 2.0


def test_bandit_select_arm_returns_valid():
    bandit = ThompsonBandit()
    fv = FeatureVector(context_score=70, phase_score=0.7, solidarity=0.8, aligned_count=3, session_quality=0.9)
    arm = bandit.select_arm(fv)
    assert arm in BANDIT_ARMS


def test_bandit_prefers_high_reward_arm():
    """Arm avec récompense élevée doit être favorisé."""
    bandit = ThompsonBandit(rng=__import__('random').Random(42))
    # Manual : update A1_BOOST 10× avec reward=1.0
    for _ in range(10):
        bandit.update("A1_BOOST", 1.0)
    # Update NEUTRAL 10× avec reward=0.2
    for _ in range(10):
        bandit.update("NEUTRAL", 0.2)
    # Now A1_BOOST should be picked most of the time
    picks = [bandit.select_arm(FeatureVector()) for _ in range(100)]
    n_boost = sum(1 for p in picks if p == "A1_BOOST")
    assert n_boost > 80  # au moins 80/100


def test_bandit_epsilon_exploration():
    """epsilon=10% : 1/10 picks uniform random parmi les arms."""
    import random
    bandit = ThompsonBandit(rng=random.Random(0))
    picks_eps = [bandit.select_arm(FeatureVector(), epsilon=1.0) for _ in range(100)]
    # Avec epsilon=1.0, distribution devrait être ~uniform parmi 3 arms
    counts = {arm: sum(1 for p in picks_eps if p == arm) for arm in BANDIT_ARMS}
    for arm in BANDIT_ARMS:
        assert 20 <= counts[arm] <= 50  # ~33 chacun


# ─────────────────────────────────────────────────────────────────────
# 4. ADWIN DRIFT DETECTOR
# ─────────────────────────────────────────────────────────────────────

def test_adwin_no_drift_stable():
    """WR stable ~0.6, pas de drift."""
    adwin = ADWINDriftDetector()
    drift_count = 0
    for _ in range(60):
        if adwin.add(0.6):
            drift_count += 1
    assert drift_count == 0


def test_adwin_drift_detected_sudden_shift():
    """WR shift 0.95 → 0.10 doit être détecté (delta=0.1, fenêtre 30)."""
    adwin = ADWINDriftDetector(delta=0.1)
    for _ in range(50):
        adwin.add(0.95)
    drift_detected = False
    for _ in range(50):
        if adwin.add(0.10):
            drift_detected = True
            break
    assert drift_detected
    assert adwin.drift_count >= 1


def test_adwin_rejects_out_of_range():
    adwin = ADWINDriftDetector()
    assert adwin.add(2.0) is False  # out of range
    assert adwin.add(-0.5) is False


def test_adwin_max_window_cap():
    adwin = ADWINDriftDetector(max_window=50)
    for i in range(100):
        adwin.add(0.5)
    assert adwin.size() <= 50


# ─────────────────────────────────────────────────────────────────────
# 5. RL ADAPTER — KILL SWITCH (R10)
# ─────────────────────────────────────────────────────────────────────

def test_rl_adapter_default_shadow_mode():
    """CEO spec : mode par défaut = SHADOW."""
    rl = RLAdapter()
    assert rl.mode == RLMode.SHADOW
    assert rl.kill_switch_active is False


def test_kill_switch_activates_at_5pct_dd():
    rl = RLAdapter(max_dd_pct=5.0)
    # Génère une perte de 6% sur equity peak=100 → DD=6% > 5%
    rl.peak_equity_pips = 100.0
    rl.cumulative_pnl_pips = 100.0  # au peak
    dd = rl._update_dd(-6.0)  # perte de 6 pips → equity=94, DD=(100-94)/100=6%
    assert rl.kill_switch_active
    assert "DD=" in rl.kill_switch_reason
    assert rl.mode == RLMode.DISABLED


def test_kill_switch_decide_returns_baseline():
    rl = RLAdapter()
    rl.kill_switch_active = True
    rl.mode = RLMode.DISABLED
    fv = FeatureVector(context_score=80)
    final, arm, _ = rl.decide_signal_level(fv, baseline_level="A1")
    assert final == "A1"
    assert arm == "DISABLED_KILL_SWITCH"


# ─────────────────────────────────────────────────────────────────────
# 6. SHADOW LOG
# ─────────────────────────────────────────────────────────────────────

def test_shadow_trade_default():
    t = ShadowTrade(
        trade_id="TR1", timestamp="2026-08-05T10:00:00Z",
        pair="GBPUSD", arm_chosen="A1_BOOST", reward=0.6, pnl_pips=10.0,
        shadow_signal_level="A1", baseline_signal_level="A2",
    )
    d = t.as_dict()
    assert d["pair"] == "GBPUSD"
    assert d["reward"] == 0.6
    assert "feature_vector" in d


def test_compute_reward_normalization():
    """+50p → 1.0, 0 → 0.5, -50p → 0.0."""
    assert RLAdapter.compute_reward(50.0) == 1.0
    assert RLAdapter.compute_reward(0.0) == 0.5
    assert RLAdapter.compute_reward(-50.0) == 0.0


def test_compute_reward_clip():
    assert RLAdapter.compute_reward(100.0) == 1.0
    assert RLAdapter.compute_reward(-100.0) == 0.0


def test_log_shadow_trade_updates_bandit():
    rl = RLAdapter()
    fv = FeatureVector(context_score=80, phase_score=0.7, solidarity=0.8, aligned_count=3, session_quality=0.9)
    rl.log_shadow_trade(
        trade_id="TR1", pair="GBPUSD", timestamp="2026-08-05T10:00:00Z",
        feature_vector=fv, arm_chosen="A1_BOOST",
        baseline_level="A2", shadow_level="A1", pnl_pips=10.0,
    )
    assert rl.bandit.total_pulls == 1
    assert rl.shadow_log[0].pair == "GBPUSD"


def test_log_shadow_trade_triggers_drift():
    """WR shift 1.0 → 0.0 sur 60 trades → drift détecté."""
    rl = RLAdapter()
    fv = FeatureVector(context_score=50)
    for i in range(60):
        pnl = 5.0 if i < 30 else -10.0  # wins puis losses massives
        rl.log_shadow_trade(
            trade_id=f"TR{i}", pair="GBPUSD", timestamp="2026-08-05T10:00:00Z",
            feature_vector=fv, arm_chosen="A1_BOOST",
            baseline_level="A2", shadow_level="A1", pnl_pips=pnl,
        )
    drifts = sum(1 for t in rl.shadow_log if t.drift_detected)
    assert drifts >= 1


# ─────────────────────────────────────────────────────────────────────
# 7. SHADOW STATS / GATE CEO
# ─────────────────────────────────────────────────────────────────────

def test_shadow_stats_empty():
    rl = RLAdapter()
    stats = rl.get_shadow_stats()
    assert stats["n_trades"] == 0
    assert stats["gate_passed"] is False


def test_shadow_stats_30_trades_pass():
    """30 trades shadow avec WR > baseline last 30 → gate passe."""
    rl = RLAdapter()
    fv = FeatureVector(context_score=70)
    for i in range(30):
        # Trades gagnants
        rl.log_shadow_trade(
            trade_id=f"TR{i}", pair="GBPUSD", timestamp="2026-08-05T10:00:00Z",
            feature_vector=fv, arm_chosen="A1_BOOST",
            baseline_level="A2", shadow_level="A1", pnl_pips=10.0,
        )
    stats = rl.get_shadow_stats()
    assert stats["wr_shadow"] == 1.0
    assert stats["gate_passed"] is True


def test_get_state_serializable():
    rl = RLAdapter()
    state = rl.get_state()
    d = state.as_dict()
    assert "bandit_arms" in d
    assert d["mode"] == "SHADOW"
    s = json.dumps(d)
    parsed = json.loads(s)
    assert parsed["mode"] == "SHADOW"


# ─────────────────────────────────────────────────────────────────────
# 8. PERSISTENCE DB
# ─────────────────────────────────────────────────────────────────────

def test_shadow_persistence_db(tmp_path):
    db_path = str(tmp_path / "test_rl.db")
    rl = RLAdapter(db_path=db_path)
    fv = FeatureVector(context_score=70)
    rl.log_shadow_trade(
        trade_id="TR_PERSIST", pair="EURUSD", timestamp="2026-08-05T10:00:00Z",
        feature_vector=fv, arm_chosen="NEUTRAL",
        baseline_level="A1", shadow_level="A1", pnl_pips=5.0,
    )
    # Vérifie que la table existe
    con = sqlite3.connect(db_path, timeout=10)
    cur = con.cursor()
    cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{SHADOW_TABLE_NAME}'")
    assert cur.fetchone() is not None
    cur.execute(f"SELECT COUNT(*) FROM {SHADOW_TABLE_NAME}")
    n = cur.fetchone()[0]
    assert n == 1
    con.close()


# ─────────────────────────────────────────────────────────────────────
# 9. DECIDE SIGNAL LEVEL
# ─────────────────────────────────────────────────────────────────────

def test_decide_arm_boost_a2_to_a1():
    """Force bandit à choisir A1_BOOST en boostant le posterior."""
    rl = RLAdapter()
    # Force A1_BOOST à dominer : 50 updates reward=1.0
    for _ in range(50):
        rl.bandit.update("A1_BOOST", 1.0)
    for _ in range(50):
        rl.bandit.update("A1_DAMPEN", 0.0)
    for _ in range(50):
        rl.bandit.update("NEUTRAL", 0.5)
    fv = FeatureVector(context_score=80)
    final, arm, _ = rl.decide_signal_level(fv, baseline_level="A2")
    assert arm == "A1_BOOST"
    assert final == "A1"


def test_decide_arm_dampen_a1_to_a2():
    """Force bandit à toujours choisir A1_DAMPEN."""
    rl = RLAdapter()
    # Update A1_DAMPEN pour le rendre dominant
    for _ in range(20):
        rl.bandit.update("A1_DAMPEN", 1.0)
    for _ in range(20):
        rl.bandit.update("A1_BOOST", 0.0)
    fv = FeatureVector(context_score=50)
    final, arm, _ = rl.decide_signal_level(fv, baseline_level="A1")
    assert arm == "A1_DAMPEN"
    assert final == "A2"

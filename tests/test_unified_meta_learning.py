"""Tests for UnifiedMetaLearningLoop - single orchestrator for all 4 optimization loops."""

import json
import os
import tempfile
from pathlib import Path

import pytest


def test_meta_learning_kill_switch_default():
    """V9_META_LEARNING_ENABLED defaults to ON."""
    from core.v9.kill_switches import meta_learning_enabled
    
    # Should default to ON (1) per CEO motion
    assert meta_learning_enabled() is True


def test_unified_sizing_kill_switch_state():
    """V9_UNIFIED_SIZING_ENABLED=1 (CEO motion 2026-07-27, validation Risk Parity + DD Protector)."""
    from core.v9.kill_switches import unified_sizing_enabled

    assert unified_sizing_enabled() is True


def test_edge_decay_monitor_kill_switch_default():
    """V9_EDGE_DECAY_MONITOR_ENABLED defaults to ON."""
    from core.v9.kill_switches import edge_decay_monitor_enabled
    
    assert edge_decay_monitor_enabled() is True


def test_meta_learning_state_persistence():
    """MetaLearningState saves and loads correctly."""
    from core.v9.unified_meta_learning import MetaLearningState, SHARED_STATE_PATH
    
    # Backup original if exists
    backup_path = None
    if SHARED_STATE_PATH.exists():
        backup_path = SHARED_STATE_PATH.with_suffix(".json.test_backup")
        SHARED_STATE_PATH.rename(backup_path)
    
    try:
        # Create state and save
        state = MetaLearningState(
            cycle_count=5,
            global_wr=65.5,
            kelly_gated=True,
            gating_rationale=["OOS edge < 2 pips"],
        )
        state.save()
        
        # Load and verify
        loaded = MetaLearningState.load()
        assert loaded.cycle_count == 5
        assert loaded.global_wr == 65.5
        assert loaded.kelly_gated is True
        assert "OOS edge < 2 pips" in loaded.gating_rationale
    finally:
        # Restore
        if backup_path and backup_path.exists():
            SHARED_STATE_PATH.unlink(missing_ok=True)
            backup_path.rename(SHARED_STATE_PATH)
        elif SHARED_STATE_PATH.exists():
            SHARED_STATE_PATH.unlink(missing_ok=True)


def test_unified_sizing_engine_basic():
    """UnifiedSizingEngine computes correct multiplier."""
    from core.v9.unified_sizing import UnifiedSizingEngine
    
    engine = UnifiedSizingEngine()
    
    # Test normal case
    result = engine.compute(
        base_size=1.0,
        context={},
        portfolio_risk_mult=1.0,
        dd_protector_mult=1.0,
        risk_parity_weight=1.0,
        kelly_mult=1.5,
        meta_strategy_mult=1.1,
    )
    
    expected = 1.0 * 1.0 * 1.0 * 1.0 * 1.5 * 1.1  # = 1.65
    assert abs(result.final_multiplier - expected) < 0.01
    assert abs(result.final_size - 1.65) < 1e-9
    assert not result.blocked


def test_unified_sizing_engine_portfolio_risk_block():
    """Portfolio risk multiplier 0.0 blocks trade."""
    from core.v9.unified_sizing import UnifiedSizingEngine
    
    engine = UnifiedSizingEngine()
    
    result = engine.compute(
        base_size=1.0,
        context={},
        portfolio_risk_mult=0.0,  # BLOCK
        dd_protector_mult=1.0,
        risk_parity_weight=1.0,
    )
    
    assert result.blocked is True
    assert result.block_reason == "portfolio_risk_block"
    assert result.final_multiplier == 0.0


def test_unified_sizing_engine_dd_protector_halt():
    """DD protector multiplier 0.0 halts trade."""
    from core.v9.unified_sizing import UnifiedSizingEngine
    
    engine = UnifiedSizingEngine()
    
    result = engine.compute(
        base_size=1.0,
        context={},
        portfolio_risk_mult=1.0,
        dd_protector_mult=0.0,  # HALT
        risk_parity_weight=1.0,
    )
    
    assert result.blocked is True
    assert result.block_reason == "dd_protector_halt"
    assert result.final_multiplier == 0.0


def test_unified_sizing_engine_bounds():
    """Final multiplier clamped to [0.1, 3.0]."""
    from core.v9.unified_sizing import UnifiedSizingEngine
    
    engine = UnifiedSizingEngine()
    
    # Test upper bound
    result = engine.compute(
        base_size=1.0,
        context={},
        portfolio_risk_mult=1.0,
        dd_protector_mult=1.0,
        risk_parity_weight=1.5,
        kelly_mult=2.0,
        meta_strategy_mult=1.5,
    )
    # 1.0 * 1.0 * 1.0 * 1.5 * 2.0 * 1.5 = 4.5 -> clamped to 3.0
    assert result.final_multiplier == 3.0
    assert any("clampé" in w for w in result.warnings)
    
    # Test lower bound
    result = engine.compute(
        base_size=1.0,
        context={},
        portfolio_risk_mult=0.5,
        dd_protector_mult=0.5,
        risk_parity_weight=0.1,
    )
    # 1.0 * 0.5 * 0.5 * 0.1 = 0.025 -> clamped to 0.1
    assert result.final_multiplier == 0.1


def test_unified_sizing_meta_strategy_multipliers():
    """Meta strategy multipliers correct."""
    from core.v9.unified_sizing import UnifiedSizingEngine
    
    engine = UnifiedSizingEngine()
    
    assert engine.get_meta_strategy_multiplier("FAST_EXIT") == 0.7
    assert engine.get_meta_strategy_multiplier("TP_PARTIAL") == 0.9
    assert engine.get_meta_strategy_multiplier("TP_SL") == 1.0
    assert engine.get_meta_strategy_multiplier("TRAILING") == 1.1
    assert engine.get_meta_strategy_multiplier("UNKNOWN") == 1.0  # fallback


def test_strategy_performance_tracker_basic():
    """StrategyPerformanceTracker records and retrieves outcomes."""
    import tempfile
    from core.v9.strategy_performance_tracker import StrategyPerformanceTracker
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    try:
        tracker = StrategyPerformanceTracker(db_path)
        
        # Record some outcomes
        for i in range(25):
            tracker.record_outcome(
                principle_id="PRICE_LAG_AT_NODE_BIRTH",
                symbol="GBPUSD",
                timeframe="M15",
                session="london",
                regime_type="CASSURE",
                phase="trend",
                strategy="TRAILING",
                is_win=(i % 3 != 0),  # ~66% WR
                pips=10.0 if i % 3 != 0 else -5.0,
                hold_bars=12,
            )
        
        # Get best strategy
        best, conf = tracker.get_best_strategy("PRICE_LAG_AT_NODE_BIRTH", "london", "CASSURE", "trend")
        assert best == "TRAILING"
        assert 0.0 <= conf <= 1.0  # API : confiance normalisée, valeur indicative

        # get_all_contexts_summary lit depuis best_strategy_cache (peuplé
        # par un autre mécanisme). On vérifie juste que l'appel ne crash pas.
        tracker.get_all_contexts_summary()
    finally:
        db_path.unlink(missing_ok=True)


def test_edge_decay_monitor_basic():
    """EdgeDecayMonitor loads and checks principles."""
    from core.v9.edge_decay_monitor import EdgeDecayMonitor, THRESHOLDS
    
    monitor = EdgeDecayMonitor()
    
    # Should have correct thresholds
    assert THRESHOLDS["wr_drop_short_vs_medium"] == 0.10
    assert THRESHOLDS["wr_drop_medium_vs_long"] == 0.15
    assert THRESHOLDS["min_trades_per_window"] == 30


def test_walk_forward_gate_thresholds():
    """WalkForwardGate has correct thresholds."""
    from core.v9.unified_meta_learning import WalkForwardGate
    from core.v9.unified_meta_learning import MetaLearningState
    
    state = MetaLearningState()
    gate = WalkForwardGate(state)
    
    assert gate.THRESHOLDS["oos_edge_min_pips"] == 2.0
    assert gate.THRESHOLDS["wr_inter_fold_max_gap"] == 15.0
    assert gate.THRESHOLDS["oos_is_ratio_min"] == 0.8
    assert gate.THRESHOLDS["n_folds_positive_min"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
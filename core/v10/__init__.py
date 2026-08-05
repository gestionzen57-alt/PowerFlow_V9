"""V10 — Système cognitif aligné sur la lecture TA humaine.

Modules : Force (F1-F5), Structure (S1-S9), Contexte (C1-C7), Orchestrateur,
Currency Pairs (mapping devises/paires), Currency Strength (moteur Fatman),
VSA Engine (Wyckoff), Confluence Engine, Signal Scorer, MT5 Bridge.
"""
from .v10_force import ForceResult, compute_force
from .v10_structure import StructureResult, compute_structure
from .v10_context import ContextResult, compute_context
from .v10_currency_pairs import (
    PAIRS_USD, CURRENCIES, INVERSION_MAP,
    sign, pairs_for, all_supported_pairs, all_supported_currencies,
)
from .v10_vsa import VSAState, VSAEngineState, compute_vsa, compute_vsa_series
from .v10_confluence import (
    ConflSummary,
    ConfBias,
    compute_confluence,
    compute_confluence_multi_pair,
    DEFAULT_TF_WEIGHTS,
    DEFAULT_BRIDGE_TFS,
    SCORE_A1_THRESHOLD,
    SCORE_A2_THRESHOLD,
    SCORE_A3_THRESHOLD,
)

from .v10_signal_scorer import (
    EnhancedSignal,
    score_enhanced_signal,
    DEFAULT_CRITERIA_WEIGHTS,
    ACTIVE_SESSIONS,
)
from .v10_orchestrator import (
    V10Signal,
    compose_signal,
    compose_enhanced_signal,
    compose_enhanced_signal_with_fatman,
    SETUP_RANK,
)
from .v10_fatman_db_reader import (
    FatmanLiveState,
    FatmanSource,
    Momentum,
    get_fatman_live,
    get_all_fatman_live,
    get_fatman_with_fallback,
    freshness_check,
)
from .v10_market_regime import (
    RegimeState,
    RegimeReport,
    detect_regime,
    apply_regime_to_signal,
)
from .v10_spread_guard import (
    SpreadState,
    SpreadSource,
    check_spread,
    apply_spread_to_signal,
)
from .v10_liquidity_map import (
    LiquidityZone,
    LiquidityMap,
    ZoneType,
    ZoneSide,
    get_liquidity_map,
    liquidity_bonus_malus,
)
from .v10_delta_flow import (
    DeltaState,
    DeltaDirection,
    DeltaSource,
    compute_delta,
    delta_bonus_malus,
)
from .v10_session_filter import (
    SessionName,
    SessionQuality,
    get_session_quality,
    apply_session_to_signal,
)
from .v10_ict_ote import (
    KillZone,
    OteBias,
    OteSetup,
    OTE_LOW,
    OTE_HIGH,
    HIGH_CONVICTION_THRESHOLD,
    compute_ict_ote,
    apply_ote_to_signal,
)
from .v10_regime_hmm import (
    Regime,
    RegimeResult,
    detect_hmm_regime,
    detect_change_points,
    compose_regime_signal,
)
from .v10_smc import (
    SMCStructure,
    OrderBlockSide,
    FvgSide,
    SmcResult,
    detect_smc,
    smc_to_signal_level,
)
from .v10_filter_compositor import (
    FilterTrace,
    CompositorResult,
    compose_filters,
)
from .v10_vol_forecast import (
    VolForecast,
    forecast_vol,
    sl_tp_from_vol,
)
from .v10_wyckoff_consolidated import (
    WyckoffState,
    WyckoffConsolidated,
    consolidate_wyckoff,
)
from .v10_error_learner import (
    TradeOutcome,
    ErrorLearnerState,
    ErrorLearner,
    ADWINLikeDrift,
)
from .v10_strategy_layers import (
    StrategyLayersResult,
    apply_strategy_layers,
    apply_strategy_layers_to_signal,
)
from .v10_auto_recalibrator import (
    RecalibDecision,
    should_recalibrate,
    run_auto_recalibration,
)
from .v10_net_exposure import (
    Position as NetPosition,
    NetExposureResult,
    ExposureGate,
    compute_net_exposure,
    find_directly_opposed,
    exposure_gate,
)
from .v10_risk_shield import (
    RiskShieldDecision,
    evaluate_risk_shield,
)
from .v10_decision_pipeline import (
    PipelineDecision,
    decide_entry,
)
from .v10_decision_log import (
    DecisionRecord,
    DecisionLogger,
    summarize_decisions,
)
from .v10_edge_validator import (
    WalkForwardReport,
    WindowResult,
    TradeResult,
    Verdict,
    run_walk_forward,
)
from .v10_market_context_global import (
    Cycle, Phase,
    CycleState, Coalition, AntagonismEntry, AntagonismMap,
    DivergenceMap, MarketContext,
    PAIRS_USD_ANTAGONISM, TF_DIVERGENCE,
    read_cycle, detect_coalition, score_antagonism,
    filter_divergence, validate_context, compute_market_context,
)
# Phase 17+21 — Bayesian Recalibrator (par paire + par (paire, TF))
from .v10_bayesian_recalibrator import (
    RecalibrationReport,
    PairThreshold,
    PairTFThreshold,
    compute_recalibration,
    compute_recalibration_by_pair_tf,
    write_thresholds_json,
    load_thresholds_json,
    write_thresholds_pair_tf_json,
    load_thresholds_pair_tf_json,
    DEFAULT_THRESHOLDS,
)
# Phase 18 — RL Adapter (extension 9.2 run_shadow_session)
from .v10_rl_adapter import (
    ShadowSessionReport,
    run_shadow_session,
    simulate_shadow_trade,
)
# Phase 20++ — V10 Force Native
from .v10_force_native import (
    NativeForceFeatures,
    NativeForceReport,
    compute_force_native_pnl,
    compute_force_native_features,
    compute_native_force_report,
    load_snapshots_from_db,
    demo_run,
)
# Phase 11+ — Compression-Extension VSA (alias demo_vsa vs demo_run force_native)
from .v10_compression_extension import (
    TFVSAState,
    VSASignalReport,
    compute_vsa_signal,
    compute_tf_vsa_state,
    load_multi_tf_from_db,
    demo_run as demo_vsa,
)

# Lazy MT5 bridge import (R6 fail-open si MetaTrader5 non installé)
try:
    from .v10_mt5_bridge import (  # noqa: F401
        MT5BridgeState,
        is_mt5_available as _is_mt5_available,
        initialize as _mt5_initialize,
        shutdown as _mt5_shutdown,
        get_bars_with_fallback as _get_bars_with_fallback,
    )
    _MT5_BRIDGE_AVAILABLE = True
except ImportError:
    _MT5_BRIDGE_AVAILABLE = False

__all__ = [
    "ForceResult", "compute_force",
    "StructureResult", "compute_structure",
    "ContextResult", "compute_context",
    "PAIRS_USD", "CURRENCIES", "INVERSION_MAP",
    "sign", "pairs_for",
    "all_supported_pairs", "all_supported_currencies",
    "VSAState", "VSAEngineState", "compute_vsa", "compute_vsa_series",
    "ConflSummary", "ConfBias", "compute_confluence",
    "compute_confluence_multi_pair",
    "DEFAULT_TF_WEIGHTS", "DEFAULT_BRIDGE_TFS",
    "SCORE_A1_THRESHOLD", "SCORE_A2_THRESHOLD", "SCORE_A3_THRESHOLD",
    "EnhancedSignal", "score_enhanced_signal",
    "DEFAULT_CRITERIA_WEIGHTS", "ACTIVE_SESSIONS",
    "V10Signal", "compose_signal", "compose_enhanced_signal",
    "compose_enhanced_signal_with_fatman", "SETUP_RANK",
    "FatmanLiveState", "FatmanSource", "Momentum",
    "get_fatman_live", "get_all_fatman_live", "get_fatman_with_fallback",
    "freshness_check",
    "RegimeState", "RegimeReport", "detect_regime",
    "apply_regime_to_signal",
    "SpreadState", "SpreadSource", "check_spread",
    "apply_spread_to_signal",
    "LiquidityZone", "LiquidityMap", "ZoneType", "ZoneSide",
    "get_liquidity_map", "liquidity_bonus_malus",
    "DeltaState", "DeltaDirection", "DeltaSource",
    "compute_delta", "delta_bonus_malus",
    "SessionName", "SessionQuality",
    "get_session_quality", "apply_session_to_signal",
    "WalkForwardReport", "WindowResult", "TradeResult", "Verdict",
    "run_walk_forward",
    "Cycle", "Phase",
    "CycleState", "Coalition", "AntagonismEntry", "AntagonismMap",
    "DivergenceMap", "MarketContext",
    "PAIRS_USD_ANTAGONISM", "TF_DIVERGENCE",
    "read_cycle", "detect_coalition", "score_antagonism",
    "filter_divergence", "validate_context", "compute_market_context",
    "MT5BridgeState",
    # Phase 17 — Bayesian Recalibrator
    "compute_recalibration",
    "RecalibrationReport", "PairThreshold",
    "write_thresholds_json", "load_thresholds_json",
    "DEFAULT_THRESHOLDS",
    # Phase 21 — Recalibration by (pair, TF)
    "compute_recalibration_by_pair_tf",
    "PairTFThreshold", "ShadowSessionReport",
    "write_thresholds_pair_tf_json", "load_thresholds_pair_tf_json",
    # Phase 18 — RL Adapter (extension 9.2 run_shadow_session)
    "run_shadow_session", "simulate_shadow_trade",
    # Phase 20++ — V10 Force Native
    "compute_force_native_pnl", "compute_force_native_features",
    "compute_native_force_report", "load_snapshots_from_db",
    "demo_run",
    "NativeForceFeatures", "NativeForceReport",
    # Phase 11+ — Compression-Extension VSA
    "compute_vsa_signal", "compute_tf_vsa_state",
    "load_multi_tf_from_db", "demo_vsa",
    "VSAState", "TFVSAState", "VSASignalReport",
] 

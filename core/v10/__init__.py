"""V10 — Système cognitif aligné sur la lecture TA humaine.

Modules : Force (F1-F5), Structure (S1-S9), Contexte (C1-C7), Orchestrateur,
Currency Pairs (mapping devises/paires), Currency Strength (moteur Fatman),
VSA Engine (Wyckoff), Confluence Engine, Signal Scorer, MT5 Bridge.
"""
from .v10_auto_recalibrator import (
    RecalibDecision,
    run_auto_recalibration,
)
from .v10_calibrate_apply import (
    ACTIVE_SEUILS_NAME,
    apply_to_decision_config,
    ensure_active_thresholds,
    find_recalibrated_thresholds,
)
from .v10_confluence import (
    DEFAULT_BRIDGE_TFS,
    DEFAULT_TF_WEIGHTS,
    SCORE_A1_THRESHOLD,
    SCORE_A2_THRESHOLD,
    SCORE_A3_THRESHOLD,
    ConfBias,
    ConflSummary,
    compute_confluence,
    compute_confluence_multi_pair,
)
from .v10_context import ContextResult, compute_context
from .v10_currency_pairs import (
    CURRENCIES,
    INVERSION_MAP,
    PAIRS_USD,
    all_supported_currencies,
    all_supported_pairs,
    pairs_for,
    sign,
)
from .v10_decision_log import (
    DecisionLogger,
    DecisionRecord,
    summarize_decisions,
)
from .v10_decision_pipeline import (
    PipelineDecision,
    decide_entry,
)
from .v10_delta_flow import (
    DeltaDirection,
    DeltaSource,
    DeltaState,
    compute_delta,
    delta_bonus_malus,
)
from .v10_edge_selector import (
    DEFAULT_MIN_TRADES,
    DEFAULT_MIN_WR,
    EdgeSelector,
)
from .v10_error_learner import (
    ErrorLearner,
    LearnerState,
    TradeOutcome,
)
from .v10_fatman_db_reader import (
    FatmanLiveState,
    FatmanSource,
    Momentum,
    freshness_check,
    get_all_fatman_live,
    get_fatman_live,
    get_fatman_with_fallback,
)
from .v10_filter_compositor import (
    CompositorResult,
    FilterTrace,
    compose_filters,
)
from .v10_force import ForceResult, compute_force
from .v10_fractal_context import (
    CONFLUENCE_MIN,
    DIVERGENCE_RATIO_FAST,
    FastCinematics,
    FractalConfluence,
    FractalSignal,
    compute_fast_cinematics,
    compute_fractal_confluence,
    fractal_signal,
)
from .v10_grammar_v9 import (
    GrammarSignal,
    evaluate_grammar_v9,
    leader_follower,
    lock,
    opposition,
    pullback,
    respiration,
    tension,
)
from .v10_ict_ote import (
    HIGH_CONVICTION_THRESHOLD,
    OTE_HIGH,
    OTE_LOW,
    KillZone,
    OteBias,
    OteSetup,
    apply_ote_to_signal,
    compute_ict_ote,
)
from .v10_learning_persistence import (
    LearningPersistence,
    dict_to_learner,
    learner_to_dict,
)
from .v10_liquidity_map import (
    LiquidityMap,
    LiquidityZone,
    ZoneSide,
    ZoneType,
    get_liquidity_map,
    liquidity_bonus_malus,
)
from .v10_market_regime import (
    RegimeReport,
    RegimeState,
    apply_regime_to_signal,
    detect_regime,
)
from .v10_net_exposure import (
    ExposureGate,
    NetExposureResult,
    Position as NetPosition,
    compute_net_exposure,
    exposure_gate,
    find_directly_opposed,
)
from .v10_orchestrator import (
    SETUP_RANK,
    V10Signal,
    compose_enhanced_signal,
    compose_enhanced_signal_with_fatman,
    compose_signal,
)
from .v10_regime_hmm import (
    Regime,
    RegimeResult,
    compose_regime_signal,
    detect_change_points,
    detect_hmm_regime,
)
from .v10_risk_shield import (
    RiskShieldDecision,
    evaluate_risk_shield,
)
from .v10_session_filter import (
    SessionName,
    SessionQuality,
    apply_session_to_signal,
    get_session_quality,
)
from .v10_signal_scorer import (
    ACTIVE_SESSIONS,
    DEFAULT_CRITERIA_WEIGHTS,
    EnhancedSignal,
    score_enhanced_signal,
)
from .v10_smc import (
    FvgSide,
    OrderBlockSide,
    SmcResult,
    SMCStructure,
    detect_smc,
    smc_to_signal_level,
)
from .v10_spread_guard import (
    SpreadSource,
    SpreadState,
    apply_spread_to_signal,
    check_spread,
)
from .v10_strategy_layers import (
    StrategyLayersResult,
    apply_strategy_layers,
    apply_strategy_layers_to_signal,
)
from .v10_structure import StructureResult, compute_structure
from .v10_vol_forecast import (
    VolForecast,
    forecast_vol,
    sl_tp_from_vol,
)
from .v10_vsa import VSAEngineState, VSAState, compute_vsa, compute_vsa_series
from .v10_wyckoff_consolidated import (
    WyckoffConsolidated,
    WyckoffState,
    consolidate_wyckoff,
)

try:
    from .v10_grammar_v9_extra import (
        GrammarSignal as GrammarSignalExtra,
        adaptive_vol_gate,
        elastic_breath,
        evaluate_grammar_v9_extra,
        exhaustion,
        node_birth,
        velocity_climax_guard,
    )

except ImportError:  # pragma: no cover — archivé dans _deprecated
    pass
try:
    from .v10_grammar_v9_final import (
        GrammarSignal as GrammarSignalFinal,
        contexte,
        croisement,
        croisement_confirmation,
        evaluate_grammar_v9_final,
        gravity_respring,
        power_angle_break,
        raw_node_birth,
        signal_open,
    )

except ImportError:  # pragma: no cover — archivé dans _deprecated
    pass
# Phase 17+21 — Bayesian Recalibrator (par paire + par (paire, TF))
from .v10_bayesian_recalibrator import (
    DEFAULT_THRESHOLDS,
    PairTFThreshold,
    PairThreshold,
    RecalibrationReport,
    compute_recalibration,
    compute_recalibration_by_pair_tf,
    load_thresholds_json,
    load_thresholds_pair_tf_json,
    write_thresholds_json,
    write_thresholds_pair_tf_json,
)
from .v10_behavior_rag import (
    ATTR_WEIGHTS,
    analogous_behaviors,
)
from .v10_behavior_registry import (
    DEFAULT_DB as BEHAVIOR_DB,
    query_coherence,
    record_behavior,
    registry_summary,
)
from .v10_coherence_audit import (
    READING_MODULES,
    audit_orphans,
)

# Phase 11+ — Compression-Extension VSA (alias demo_vsa vs demo_run force_native)
from .v10_compression_extension import (
    TFVSAState,
    VSASignalReport,
    compute_tf_vsa_state,
    compute_vsa_signal,
    demo_run as demo_vsa,
    load_multi_tf_from_db,
)
from .v10_cortex import (
    CortexInterpretation,
    decide,
    interpret,
)
from .v10_cortex_enrich import (
    enrich_interp,
)
from .v10_edge_validator import (
    TradeResult,
    Verdict,
    WalkForwardReport,
    WindowResult,
    run_walk_forward,
)

# Phase 20++ — V10 Force Native
from .v10_force_native import (
    NativeForceFeatures,
    NativeForceReport,
    compute_force_native_features,
    compute_force_native_pnl,
    compute_native_force_report,
    demo_run,
    load_snapshots_from_db,
)
from .v10_learning_continuum import (
    CONV_BAND,
    EWM_FAST,
    EWM_SLOW,
    MIN_WARMUP,
    PHASE_CONVERGE,
    PHASE_DEGRADED,
    PHASE_DRIFTING,
    PHASE_LEARNING,
    PHASE_WARMING,
    SHARPE_THR,
    WR_DRIFT,
    ContinuumState,
    LearningContinuum,
)
from .v10_market_context_global import (
    PAIRS_USD_ANTAGONISM,
    TF_DIVERGENCE,
    AntagonismEntry,
    AntagonismMap,
    Coalition,
    Cycle,
    CycleState,
    DivergenceMap,
    MarketContext,
    Phase,
    compute_market_context,
    detect_coalition,
    filter_divergence,
    read_cycle,
    score_antagonism,
    validate_context,
)
from .v10_memory_bridge import (
    DEFAULT_DB as MEMORY_DB,
    get_transition_distribution,
    memory_summary,
    recall_patterns,
)

# Phase 18 — RL Adapter (extension 9.2 run_shadow_session)
from .v10_rl_adapter import (
    ShadowSessionReport,
    run_shadow_session,
    simulate_shadow_trade,
)

# Lazy MT5 bridge import (R6 fail-open si MetaTrader5 non installé)
try:
    from .v10_mt5_bridge import (  # noqa: F401
        MT5BridgeState,
        get_bars_with_fallback as _get_bars_with_fallback,
        initialize as _mt5_initialize,
        is_mt5_available as _is_mt5_available,
        shutdown as _mt5_shutdown,
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
    # Phase 12 — Fractal Context (multi-TF + cinématique)
    "FractalConfluence", "FastCinematics", "FractalSignal",
    "compute_fractal_confluence", "compute_fast_cinematics", "fractal_signal",
    "DIVERGENCE_RATIO_FAST", "CONFLUENCE_MIN",
]

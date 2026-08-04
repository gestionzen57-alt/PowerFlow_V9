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
from .v10_edge_validator import (
    WalkForwardReport,
    WindowResult,
    TradeResult,
    Verdict,
    run_walk_forward,
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
    "MT5BridgeState",
] 

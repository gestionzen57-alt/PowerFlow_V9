"""V10 — Système cognitif aligné sur la lecture TA humaine.

Modules : Force (F1-F5), Structure (S1-S9), Contexte (C1-C7), Orchestrateur,
Currency Pairs (mapping devises/paires), Currency Strength (moteur Fatman).
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
] 

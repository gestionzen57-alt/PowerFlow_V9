"""V10 — Système cognitif aligné sur la lecture TA humaine.

Modules : Force (F1-F5), Structure (S1-S9), Contexte (C1-C7), Orchestrateur.
"""
from .v10_force import ForceResult, compute_force
from .v10_structure import StructureResult, compute_structure
from .v10_context import ContextResult, compute_context

__all__ = [
    "ForceResult", "compute_force",
    "StructureResult", "compute_structure",
    "ContextResult", "compute_context",
]

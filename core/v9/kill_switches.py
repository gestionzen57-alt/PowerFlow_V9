"""kill_switches.py — Chargeur central des kill switches V9.

Lit `config/v9_kill_switches.env` et expose les valeurs via des fonctions
pures. Utilisé par tous les modules qui ont besoin de connaître l'état
des switches (orchestrator, principle_engine, shadow_evaluator, etc.).

Avant : chaque module lisait `os.environ.get("V9_xxx", "0")` — mais personne
ne chargeait le fichier `.env` dans l'environnement au runtime. Les switches
n'étaient effectifs que dans les tests (conftest).

Doctrine : R6 (ne jamais lever), R18 (zéro LLM), R25' (OFF par défaut).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / "config" / "v9_kill_switches.env"

# Cache process-local (lu une seule fois)
_switches: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _switches
    if _switches is not None:
        return _switches
    _switches = {}
    if not ENV_PATH.exists():
        return _switches
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        _switches[key.strip()] = val.strip()
    return _switches


def get(key: str, default: str = "0") -> str:
    """Retourne la valeur d'un kill switch.
    Priorité : variable d'environnement > fichier > défaut.
    """
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val
    return _load().get(key, default)


def is_enabled(key: str) -> bool:
    """Retourne True si le kill switch est activé (=="1")."""
    return get(key) == "1"


# ── Switches nommés ────────────────────────────────────────────────
def shadow_mode_enabled() -> bool:
    return is_enabled("V9_SHADOW_MODE_ENABLED")


def adaptive_thresholds_wired_enabled() -> bool:
    return is_enabled("V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED")


def trader_mini_enabled() -> bool:
    return is_enabled("V9_TRADER_MINI_ENABLED")


def auto_calibrator_enabled() -> bool:
    return is_enabled("V9_AUTO_CALIBRATOR_ENABLED")


def execution_enabled() -> bool:
    return is_enabled("V9_EXECUTION_ENABLED")


def auto_resolve_enabled() -> bool:
    return is_enabled("V9_AUTO_RESOLVE_ENABLED")


def arbiter_scorer_enabled() -> bool:
    return is_enabled("V9_ARBITER_SCORER_ENABLED")


def hitl_branching_enabled() -> bool:
    return is_enabled("V9_HITL_BRANCHING_ENABLED")

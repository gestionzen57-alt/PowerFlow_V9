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


def regime_gate_enabled() -> bool:
    """Kill switch V9_REGIME_GATE_ENABLED (défaut '0' = OFF).

    Chantier A (2026-07-18) : quand OFF, le gate régime de
    l'exploitabilité est passthrough (aucun blocage) — zéro régression.
    """
    return is_enabled("V9_REGIME_GATE_ENABLED")


def kelly_cvar_enabled() -> bool:
    """Kill switch V9_KELLY_CVAR_ENABLED (défaut '0' = OFF).

    Chantier B (2026-07-18) : quand OFF, le plafond CVaR sur le sizing
    Kelly existant est inactif — sizing inchangé, zéro régression.
    """
    return is_enabled("V9_KELLY_CVAR_ENABLED")


def cvd_enabled() -> bool:
    """Kill switch V9_CVD_ENABLED (défaut '0' = OFF).

    Chantier C (2026-07-18) : quand OFF, le CVD (Cumulative Volume Delta) n'est
    pas exposé dans la scène (cvd_cumul / cvd_divergence). La couche forces
    reste passive (parse ce que l'EA envoie, ou NULL). Zéro régression.
    """
    return is_enabled("V9_CVD_ENABLED")


def loop_breaker_enabled() -> bool:
    """Kill switch V9_LOOP_BREAKER_ENABLED — garde-fou anti-boucle re-entry.

    Câblage P0.4 (2026-07-19) : source de vérité = fichier `.env` (via get()),
    pas `os.environ` seul. Le cron paper-trade lançait le supervisor sans
    charger le `.env` → le switch était lu OFF alors que le fichier dit ON.
    """
    return is_enabled("V9_LOOP_BREAKER_ENABLED")


def live_watchdog_enabled() -> bool:
    """Kill switch V9_LIVE_WATCHDOG_ENABLED — watchdog live edgefund (Axe 6).

    Défaut OFF tant que pas d'activation explicite dans le `.env`. Activé
    2026-07-19 (motion CEO « Construis le watchdog » = mandat runtime).
    """
    return is_enabled("V9_LIVE_WATCHDOG_ENABLED")


def paper_trade_halt_enabled() -> bool:
    """Kill switch V9_PAPER_TRADE_HALT — HALT TOTAL du paper-trading (R6 fail-safe).

    Défaut OFF. Quand ON, le moteur de paper-trade ne doit rien ouvrir.
    C'est l'action de niveau P0 recommandée par le watchdog critique
    (remplace l'ancienne reco `V9_GBPUSD_LONG_ONLY=0` qui ré-autorisait
    les shorts au lieu d'arrêter — cf. audit edgefund 2026-07-19).
    """
    return is_enabled("V9_PAPER_TRADE_HALT")

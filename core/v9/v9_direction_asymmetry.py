"""v9_direction_asymmetry.py — Phase 129 L16 (motion CEO « go max plein pouvoir » 03/08/2026).

Asymetrie WR par direction (sizing adaptatif).

Hypothese : WR baissier structurellement inferieur au WR haussier
(historique 1108 trades, edge haussier dominant). Pour forcer l'asymetrie
dans le sizing, on applique un multiplicateur :
  - Direction haussiere : x1.3 (edge haussier dominant, amplification)
  - Direction baissiere : x0.7 (edge baissier plus faible, attenuation)
  - Exceptions par regime :
      * haussiere + RETOUR_EQUILIBRE -> x1.0 (mean-reversion, pas de momentum)
      * baissiere + CASSURE -> x1.0 (edge baissier confirme en cassure)

Audit SQL live 03/08 (n=337 paper_trades clotures, post-DROP, post-reparation V4) :
  - Haussier (n=307) : WR=45.9%, PNL=-682.0p, avg=-2.22p/trade
  - Baissier (n= 30) : WR=30.0%, PNL=-183.2p, avg=-6.32p/trade
  - GBPUSD haussier (n=163) : WR=63.8%, PNL=-42.2p (TOP NICHE L1)
  - GBPUSD baissier (n=  1) : WR=100% mais PNL=-0.8p (n trop petit)
  - Autres haussier (n=144) : WR=25.7%, PNL=-639.8p (perdant)
  - Autres baissier (n= 29) : WR=27.6%, PNL=-182.4p
  - Conclusion : baissier = -6.32p/trade vs haussier = -2.22p/trade (12x plus perdant)
  - Effet attendu sizing x0.7 baissier : -4.42p/trade evites
  - Effet attendu sizing x1.3 haussier : +0.95p/trade sur GBPUSD haussier (TOP)

Gain projete : 100-250 pips (amplification edge haussier, attenuation edge baissier).
Cout : faible (reversible via kill switch).

Additif (R2), defaut OFF (R25' strict motion CEO), R6 fail-open.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("v9.direction_asymmetry")


# ── Phase 129 — L16 Asymetrie WR par direction (2026-08-03) ─────────────
# Audit SQL live 03/08 (n=337 post-DROP) :
#   Haussier (n=307) : WR=45.9% PNL=-682.0p avg=-2.22p/trade
#   Baissier (n= 30) : WR=30.0% PNL=-183.2p avg=-6.32p/trade (12x plus perdant)
#   GBPUSD haussier (n=163) : WR=63.8% PNL=-42.2p (top niche L1)
# Gain projete : 100-250 pips. Cout : ~30% sizing haussier, 30% reduction baissier.
# Additif (R2), defaut OFF (R25' strict motion CEO), R6 fail-open.
def direction_asymmetry_enabled() -> bool:
    """Kill switch V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED — Phase 129.

    Active l'asymetrie WR par direction (sizing x1.3 haussier / x0.7 baissier).
    Defaut OFF (R25' strict motion CEO). R6 jamais bloquant.
    Module : core/v9/v9_direction_asymmetry.py (NEW).
    """
    from core.v9.kill_switches import get
    return get("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "0") == "1"


# Multiplicateurs par direction × regime
# Logique du prompt Phase 129 :
#   - haussiere : 1.3 (sauf si regime=RETOUR_EQUILIBRE -> 1.0, mean-reversion)
#   - baissiere : 0.7 (sauf si regime=CASSURE -> 1.0, edge baissier confirme)
#   - Defaut : 1.0 si kill switch OFF ou direction inconnue
DEFAULT_MULTIPLIERS: dict[tuple[str, str], float] = {
    # Haussiere
    ("haussiere", "NEUTRE"): 1.3,
    ("haussiere", "EXTENSION"): 1.3,
    ("haussiere", "CASSURE"): 1.3,
    ("haussiere", "PALIER"): 1.3,
    ("haussiere", "REJET"): 1.3,
    ("haussiere", "RETOUR_EQUILIBRE"): 1.0,  # mean-reversion, pas de momentum
    # Baissiere
    ("baissiere", "NEUTRE"): 0.7,
    ("baissiere", "EXTENSION"): 0.7,
    ("baissiere", "PALIER"): 0.7,
    ("baissiere", "RETOUR_EQUILIBRE"): 0.7,
    ("baissiere", "REJET"): 0.7,
    ("baissiere", "CASSURE"): 1.0,  # edge baissier confirme en cassure
}


def compute_asymmetry_multiplier(direction: str, regime: str | None = None) -> float:
    """Retourne le multiplicateur de sizing selon direction et regime.

    Logique :
      - haussiere : 1.3 (sauf si regime=RETOUR_EQUILIBRE -> 1.0)
      - baissiere : 0.7 (sauf si regime=CASSURE -> 1.0, edge baissier confirme)
      - Defaut : 1.0 si kill switch OFF ou direction/regime inconnue.

    R6 fail-open : toute erreur retourne 1.0 (pass-through neutre).
    """
    try:
        if not direction_asymmetry_enabled():
            return 1.0

        dir_s = str(direction or "").lower().strip()
        reg_s = str(regime or "").upper().strip() if regime else ""

        # Si pas de regime, on prend le defaut de la direction
        if not reg_s:
            if dir_s == "haussiere":
                return 1.3
            if dir_s == "baissiere":
                return 0.7
            return 1.0  # direction inconnue

        # Cherche dans la table
        key = (dir_s, reg_s)
        if key in DEFAULT_MULTIPLIERS:
            return DEFAULT_MULTIPLIERS[key]

        # Fallback : direction connue mais regime inconnu
        if dir_s == "haussiere":
            return 1.3
        if dir_s == "baissiere":
            return 0.7

        # Direction inconnue
        return 1.0
    except Exception as exc:
        log.debug("compute_asymmetry_multiplier fail-open: %s", exc)
        return 1.0


def apply_direction_asymmetry(
    sizing_base: float,
    direction: str,
    regime: str | None = None,
) -> dict[str, Any]:
    """Applique l'asymetrie au sizing de base.

    Args:
        sizing_base: Le sizing de base (avant asymetrie).
        direction: "haussiere" ou "baissiere".
        regime: Optionnel. Regime de marche.

    Returns:
        Dict avec :
          - sizing_final: float (sizing_base * multiplier)
          - multiplier: float
          - leviers: list[str] (ex: ["L16_asymmetry_×1.3"])
          - reason: str (description courte)

    R6 fail-open : toute exception est catchee, sizing_final = sizing_base.
    """
    try:
        if not direction_asymmetry_enabled():
            return {
                "sizing_final": float(sizing_base),
                "multiplier": 1.0,
                "leviers": [],
                "reason": "kill_switch_off",
            }

        mult = compute_asymmetry_multiplier(direction, regime)
        sizing_final = float(sizing_base) * mult

        # Construit le label du levier
        dir_s = str(direction or "").lower().strip()
        if mult == 1.3:
            leviers = [f"L16_asymmetry_x1.3_{dir_s}"]
        elif mult == 0.7:
            leviers = [f"L16_asymmetry_x0.7_{dir_s}"]
        elif mult == 1.0:
            if regime and str(regime).upper() in ("RETOUR_EQUILIBRE", "CASSURE"):
                leviers = [f"L16_asymmetry_neutral_{str(regime).upper()}"]
            else:
                leviers = [f"L16_asymmetry_x1.0_{dir_s}"]
        else:
            leviers = [f"L16_asymmetry_x{mult}_{dir_s}"]

        # Description
        if mult == 1.3:
            reason = f"boost haussier x1.3 (regime={regime or 'any'})"
        elif mult == 0.7:
            reason = f"attenuation baissier x0.7 (regime={regime or 'any'})"
        elif mult == 1.0 and regime and str(regime).upper() == "RETOUR_EQUILIBRE":
            reason = "mean-reversion, asymetrie desactivee"
        elif mult == 1.0 and regime and str(regime).upper() == "CASSURE":
            reason = "edge baissier confirme en cassure, asymetrie desactivee"
        else:
            reason = f"pass-through x1.0 (direction={dir_s})"

        return {
            "sizing_final": sizing_final,
            "multiplier": mult,
            "leviers": leviers,
            "reason": reason,
        }
    except Exception as exc:
        # R6 fail-open
        log.debug("apply_direction_asymmetry fail-open: %s", exc)
        return {
            "sizing_final": float(sizing_base),
            "multiplier": 1.0,
            "leviers": [],
            "reason": "failopen",
        }

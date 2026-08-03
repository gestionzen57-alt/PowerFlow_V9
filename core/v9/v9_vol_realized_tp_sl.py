"""v9_vol_realized_tp_sl.py — Phase 130 L13 : Adaptive TP/SL by realized volatility.

Filtre additif qui module les TP/SL adaptatifs selon la volatilité réalisée
des N dernières bougies M5. Additif (R2), défaut OFF (R25' strict), R6
jamais bloquant.

Mission CEO no-stop 03/08/2026 — sprint L11+. Plan quantique L11+.

Hypothèse : un trade pris sur un spike de volatilité (vol réalisée > 2× la
moyenne 20 bougies) doit avoir un TP/SL élargi (×1.5) pour ne pas se faire
sorter par le bruit. À l'inverse, une vol réalisée < 0.5× moyenne resserre
le TP/SL (×0.7) pour capturer les mouvements plus vite.

Gain projeté : 50-100 pips (capture des spikes vol sans casser le RR cible).

Doctrine : R2 additif, R6 fail-open, R14 git verite, R25' motion CEO.
"""
from __future__ import annotations

from typing import Sequence

from core.v9.kill_switches import get


# ── Configuration ───────────────────────────────────────────────────
VERSION = "1.0"

# Bornes multiplicateurs (R6 strict : ne jamais sortir des bornes)
TP_MIN_MULT = 0.7
TP_MAX_MULT = 1.5
SL_MIN_MULT = 0.7
SL_MAX_MULT = 1.5

# Seuil de vol spike (ratio spike / moyenne)
VOL_SPIKE_THRESHOLD = 2.0   # au-dessus : élargir
VOL_CALM_THRESHOLD = 0.5    # en-dessous : resserrer

# Fenêtre pour la moyenne de référence
VOL_LOOKBACK_BARS = 20


# ── Kill switch ──────────────────────────────────────────────────────
def vol_realized_tp_sl_enabled() -> bool:
    """Kill switch V9_HEATMAP_L13_VOL_REALIZED_TP_SL_ENABLED — Phase 130 (03/08).

    Active le module d'adaptation TP/SL par volatilité réalisée.
    Defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    Additif (R2), 0 modif core/ partagé.
    """
    return get("V9_HEATMAP_L13_VOL_REALIZED_TP_SL_ENABLED", "0") == "1"


# ── Calcul de la volatilité réalisée ────────────────────────────────
def compute_realized_vol_ratio(
    recent_ranges: Sequence[float],
    lookback: int = VOL_LOOKBACK_BARS,
) -> float:
    """Calcule le ratio volatilité récente / moyenne historique.

    Args:
        recent_ranges : Liste des ranges (high-low) des N dernières bougies,
                       du plus récent au plus ancien.
        lookback : Nombre de bougies pour la moyenne (défaut 20).

    Returns:
        Ratio vol_actuelle / vol_moyenne.
        Retourne 1.0 si données insuffisantes (R6 fail-open).
    """
    if not recent_ranges or len(recent_ranges) < 2:
        return 1.0  # R6 fail-open : pas de données → pass-through
    # Vol récente : moyenne des 5 derniers ranges
    n_recent = min(5, len(recent_ranges))
    vol_recent = sum(recent_ranges[:n_recent]) / n_recent
    # Vol moyenne : moyenne des `lookback` bougies (ou toutes si moins)
    n_avg = min(lookback, len(recent_ranges))
    vol_avg = sum(recent_ranges[:n_avg]) / n_avg
    if vol_avg <= 0:
        return 1.0  # R6 fail-open : division par zéro
    return vol_recent / vol_avg


# ── Calcul du multiplicateur TP/SL ──────────────────────────────────
def compute_tp_sl_multipliers(vol_ratio: float) -> tuple[float, float]:
    """Retourne (tp_mult, sl_mult) selon le ratio de volatilité.

    Logique :
      - vol_ratio >= VOL_SPIKE_THRESHOLD : élargir TP et SL (×1.5)
      - vol_ratio <= VOL_CALM_THRESHOLD : resserrer TP et SL (×0.7)
      - sinon : pass-through (×1.0)

    Bornes strictes : [TP_MIN_MULT, TP_MAX_MULT] et [SL_MIN_MULT, SL_MAX_MULT].
    """
    if vol_ratio >= VOL_SPIKE_THRESHOLD:
        return TP_MAX_MULT, SL_MAX_MULT
    if vol_ratio <= VOL_CALM_THRESHOLD:
        return TP_MIN_MULT, SL_MIN_MULT
    return 1.0, 1.0


# ── API principale ──────────────────────────────────────────────────
def adapt_tp_sl_by_volatility(
    tp_base: float,
    sl_base: float,
    recent_ranges: Sequence[float],
) -> dict:
    """Adapte TP/SL selon la volatilité réalisée.

    Args:
        tp_base : TP de base en pips (proposé par DynamicRiskManager).
        sl_base : SL de base en pips (idem).
        recent_ranges : Ranges récents (high-low par bougie, plus récent d'abord).

    Returns:
        dict avec :
          - tp_adjusted : float (TP adapté en pips)
          - sl_adjusted : float (SL adapté en pips)
          - tp_multiplier : float
          - sl_multiplier : float
          - vol_ratio : float
          - vol_regime : str ("spike", "calm", "normal")
          - leviers : list[str] (["L13_vol_spike"], ["L13_vol_calm"], ou [])
          - active : bool (True si L13 a appliqué un ajustement)
    """
    if not vol_realized_tp_sl_enabled():
        return {
            "tp_adjusted": tp_base,
            "sl_adjusted": sl_base,
            "tp_multiplier": 1.0,
            "sl_multiplier": 1.0,
            "vol_ratio": 1.0,
            "vol_regime": "normal",
            "leviers": [],
            "active": False,
        }

    # R6 fail-open : si pas de données, pass-through
    if not recent_ranges:
        return {
            "tp_adjusted": tp_base,
            "sl_adjusted": sl_base,
            "tp_multiplier": 1.0,
            "sl_multiplier": 1.0,
            "vol_ratio": 1.0,
            "vol_regime": "normal",
            "leviers": [],
            "active": False,
        }

    vol_ratio = compute_realized_vol_ratio(recent_ranges)
    tp_mult, sl_mult = compute_tp_sl_multipliers(vol_ratio)

    # Bornes strictes
    tp_mult = max(TP_MIN_MULT, min(TP_MAX_MULT, tp_mult))
    sl_mult = max(SL_MIN_MULT, min(SL_MAX_MULT, sl_mult))

    if tp_mult == 1.0 and sl_mult == 1.0:
        regime = "normal"
        leviers: list[str] = []
        active = False
    elif tp_mult >= TP_MAX_MULT:
        regime = "spike"
        leviers = ["L13_vol_spike_x1.5"]
        active = True
    else:  # tp_mult <= TP_MIN_MULT
        regime = "calm"
        leviers = ["L13_vol_calm_x0.7"]
        active = True

    return {
        "tp_adjusted": round(tp_base * tp_mult, 2),
        "sl_adjusted": round(sl_base * sl_mult, 2),
        "tp_multiplier": tp_mult,
        "sl_multiplier": sl_mult,
        "vol_ratio": round(vol_ratio, 3),
        "vol_regime": regime,
        "leviers": leviers,
        "active": active,
    }
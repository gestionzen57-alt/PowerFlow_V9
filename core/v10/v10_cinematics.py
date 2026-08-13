"""v10_cinematics.py — Lecture CINÉMATIQUE générique de la courbe Fatman (core).

Søn : "Tu vois des valeurs mais pas toute la cinématique — les courbes,
pics et creux." Ce module extrait de la COURBE de force (base vs quote)
pour N'IMPORTE QUELLE paire :
- pics / creux locaux et leur timing
- pente / accélération de la courbe
- DIVERGENCE force vs prix (force décline pendant que le prix pousse)
- exhaustion : pic brutal puis retombée

C'est la lecture "en courbe" qui complète la lecture "en valeur". Version
générique de scripts/v10_force_cinematics.py (qui était GBPUSD-only),
utilisable par l'edge OVERLAP (EURUSD/USDCHF/AUDUSD) et le pipeline live.

R10 : lecture only, zéro ordre.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Tuple


def _pivots(vals: List[float], window: int = 3) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """Pics/creux locaux (fenêtre window de chaque côté)."""
    n = len(vals)
    highs: List[Tuple[int, float]] = []
    lows: List[Tuple[int, float]] = []
    for i in range(window, n - window):
        v = vals[i]
        if v >= max(vals[i - window:i + window + 1]):
            highs.append((i, v))
        if v <= min(vals[i - window:i + window + 1]):
            lows.append((i, v))
    return highs, lows


def analyze_series(
    forces: List[float],
    prices: List[float],
    label: str = "",
    pip_size: float = 0.0001,
) -> Dict:
    """Analyse cinématique d'une série de force + prix (même longueur).

    Args:
        forces  : série de delta_forces (ou force base) — ordre chronologique
        prices  : série de prix (close)
        label   : nom de la série (ex: "M15 EURUSD")
        pip_size: taille d'un pip pour la paire (0.01 JPY, 0.0001 sinon)

    Retourne un dict avec : last_force, force_pic, force_creux, slope_force,
    slope_price, divergence_force_price, exhaustion_pic, acceleration,
    pic_bars_ago, creux_bars_ago.
    """
    if len(forces) < 10 or len(prices) < 10:
        return {"error": "insufficient", "label": label}

    n = len(forces)
    highs, lows = _pivots(forces)
    pic = max(highs, key=lambda x: x[1]) if highs else None
    creux = min(lows, key=lambda x: x[1]) if lows else None

    # Pentes (5 dernières barres)
    slope_force = (forces[-1] - forces[-5]) if n >= 5 else 0.0
    slope_price = (prices[-1] - prices[-5]) / (prices[-5] or 1e-9) * 100 if n >= 5 else 0.0

    # DIVERGENCE : pic de force il y a >2 barres, la force décline ensuite,
    # MAIS le prix fait un nouveau sommet récent sans confirmation.
    divergence = False
    divergence_detail = None
    for (i, v) in highs:
        if i <= n - 3:
            force_declined = forces[-1] < v - 3.0
            price_made_new_high = prices[-1] > max(prices[i + 1:]) or \
                (len(prices) > i + 1 and max(prices[i + 1:]) > max(prices[max(0, i - 3):i + 1]))
            price_near_top = (max(prices) - prices[-1]) / pip_size < 20
            if force_declined and price_made_new_high and price_near_top:
                divergence = True
                divergence_detail = {
                    "force_pic": round(v, 1), "force_pic_bars_ago": n - 1 - i,
                    "force_now": round(forces[-1], 1),
                    "price_top": round(max(prices), 5), "price_now": round(prices[-1], 5),
                }
            break

    # Exhaustion : pic récent (10 dernières barres) puis retombée
    recent_pic = None
    for (i, v) in highs:
        if i >= n - 10:
            recent_pic = (i, v)
    exhaustion = bool(recent_pic and forces[-1] < recent_pic[1] - 5.0)

    # Accélération : 2e dérivée sur 4 barres
    accel = (forces[-1] - forces[-3]) - (forces[-3] - forces[-5]) if n >= 6 else 0.0

    return {
        "label": label,
        "last_force": round(forces[-1], 1),
        "force_pic": round(pic[1], 1) if pic else None,
        "pic_bars_ago": n - 1 - pic[0] if pic else None,
        "force_creux": round(creux[1], 1) if creux else None,
        "creux_bars_ago": n - 1 - creux[0] if creux else None,
        "slope_force_5": round(slope_force, 1),
        "slope_price_5": round(slope_price, 3),
        "divergence_force_price": divergence,
        "divergence_detail": divergence_detail,
        "exhaustion_pic": exhaustion,
        "acceleration_force": round(accel, 1),
    }


def cinematics_verdict(analysis: Dict, direction: str) -> Dict:
    """Verdict cinématique pour une direction de trade (BUY/SELL).

    Règles (institutionnelles — extraction logique Søn 12/08) :
      1. DIVERGENCE contre la direction → BLOCK (piège)
      2. EXHAUSTION de la force dans le sens du trade → BLOCK (épuisement)
      3. Sinon → ALLOW

    Le delta brut donne la direction ; la cinématique filtre les faux signaux
    (pic épuisé, divergence). C'est le multiplicateur de qualité.
    """
    if "error" in analysis:
        return {"action": "ALLOW", "reason": "insufficient", "analysis": analysis}

    reasons = []
    blocked = False

    # Divergence : force décline pendant que prix pousse → piège
    if analysis.get("divergence_force_price"):
        blocked = True
        reasons.append(
            f"DIVERGENCE : force pic {analysis.get('force_pic')} → {analysis.get('last_force')} "
            f"pendant que prix fait sommet — piège {direction}"
        )

    # Exhaustion : pic récent puis retombée de la force (épuisement)
    if analysis.get("exhaustion_pic"):
        blocked = True
        reasons.append(
            f"EXHAUSTION : pic force {analysis.get('force_pic')} (il y a "
            f"{analysis.get('pic_bars_ago')} barres) puis retombée à "
            f"{analysis.get('last_force')} — épuisement {direction}"
        )

    # Accélération négative forte avec force en déclin = momentum mort
    if (not blocked and analysis.get("acceleration_force", 0) < -3.0
            and analysis.get("slope_force_5", 0) < -2.0):
        reasons.append(
            f"MOMENTUM MORT : accélération {analysis.get('acceleration_force')} "
            f"pente {analysis.get('slope_force_5')} — force qui retombe"
        )

    action = "BLOCK" if blocked else "ALLOW"
    return {
        "action": action,
        "reasons": reasons,
        "analysis": {k: v for k, v in analysis.items() if k != "divergence_detail"},
    }


def load_force_price_series(
    db_path: str,
    symbol: str,
    timeframe: str,
    limit: int = 120,
) -> Tuple[List[float], List[float], List[int]]:
    """Charge série (delta_forces, close, bar_time) depuis forces_snapshots."""
    base, quote = symbol[:3], symbol[3:6]
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = con.execute(
        f"SELECT bar_time, close, force_{base.lower()}, force_{quote.lower()} "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time ASC",
        (symbol, timeframe),
    ).fetchall()
    con.close()
    rows = rows[-limit:]
    forces = [float(r[2]) - float(r[3]) for r in rows]
    prices = [float(r[1]) for r in rows]
    bar_times = [int(r[0]) for r in rows]
    return forces, prices, bar_times

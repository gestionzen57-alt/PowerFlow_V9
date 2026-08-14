"""v10_confluence_tf.py — Score de confluence multi-TF (Pilier 2, Søn).

Søn : "les confirmations de croisement sont retardées, les zones doivent
être lues correctement avec imbrication." Le H1 confirme APRÈS le mouvement,
le M5 anticipe AVANT, le M30 confirme, le M15 exécute.

Ce module calcule un score de confluence [0..4] pour un signal M15 :
  +1 si M30 aligné (delta même direction)
  +1 si H1 aligné (delta même direction)
  +1 si M5 en extension (pente positive dans le sens du trade)
  +1 si cinématique M15 ALLOW (pas de divergence/exhaustion)

Le score module le SIZING (plus de confluence = plus de lots) au lieu de
bloquer. Un conflit H1 ne bloque pas — il réduit la taille (le H1 est en
retard, pas en erreur).

R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Tuple

from .v10_cinematics import analyze_series, cinematics_verdict


def load_tf_bars(db_path: str, symbol: str, tf: str, limit: int = 2000) -> List[dict]:
    """Barres d'un TF (chronologique ascendant) depuis forces_snapshots."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, force_eur, force_usd, force_gbp, "
        "force_jpy, force_cad, force_chf, force_aud, force_nzd "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (symbol, tf, limit),
    ).fetchall()
    con.close()
    return [dict(r) for r in reversed(rows)]


def _delta_at(b: dict, symbol: str) -> float:
    base, quote = symbol[:3], symbol[3:6]
    return float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0))


def _tf_delta_at_time(bars_tf: List[dict], symbol: str, ts: int) -> Optional[float]:
    """Delta forces du TF au moment ts (dernière barre fermée ≤ ts)."""
    best = None
    for b in bars_tf:
        if int(b["bar_time"]) <= ts:
            best = b
        else:
            break
    return _delta_at(best, symbol) if best else None


def _m5_extension(bars_m5: List[dict], symbol: str, ts: int) -> Tuple[bool, dict]:
    """M5 en extension ? (pente positive dans le sens du trade)."""
    forces, prices = [], []
    for b in bars_m5:
        if int(b["bar_time"]) <= ts:
            forces.append(_delta_at(b, symbol))
            prices.append(float(b["close"]))
    if len(forces) < 10:
        return False, {"available": False}
    pip = 0.01 if symbol.endswith("JPY") else 0.0001
    ana = analyze_series(forces, prices, label=f"{symbol} M5", pip_size=pip)
    return True, ana


def confluence_score(
    db_path: str,
    symbol: str,
    bar_time: int,
    direction: str,
    bars_m15: List[dict],
    bars_m5: Optional[List[dict]] = None,
    bars_m30: Optional[List[dict]] = None,
    bars_h1: Optional[List[dict]] = None,
) -> Dict:
    """Score de confluence [0..4] pour un signal M15.

    Args:
        db_path   : chemin DB
        symbol    : paire (EURUSD, USDCHF, AUDUSD)
        bar_time  : timestamp de la barre M15 du signal
        direction : BUY / SELL
        bars_m15  : barres M15 (pour la cinématique)
        bars_m5/m30/h1 : barres des autres TF (optionnel — chargées si None)

    Retourne : {score, max_score, components: {m30, h1, m5, m15_cine},
                detail: {...}, sizing_multiplier}
    """
    # 1. M30 aligné
    if bars_m30 is None:
        bars_m30 = load_tf_bars(db_path, symbol, "M30")
    d_m30 = _tf_delta_at_time(bars_m30, symbol, bar_time)
    m30_ok = d_m30 is not None and (d_m30 * (1 if direction == "BUY" else -1)) > 0

    # 2. H1 aligné
    if bars_h1 is None:
        bars_h1 = load_tf_bars(db_path, symbol, "H1")
    d_h1 = _tf_delta_at_time(bars_h1, symbol, bar_time)
    h1_ok = d_h1 is not None and (d_h1 * (1 if direction == "BUY" else -1)) > 0

    # 3. M5 en extension
    if bars_m5 is None:
        bars_m5 = load_tf_bars(db_path, symbol, "M5", limit=4000)
    m5_avail, m5_ana = _m5_extension(bars_m5, symbol, bar_time)
    m5_ok = False
    if m5_avail:
        slope = m5_ana.get("slope_force_5", 0.0)
        # P9 AUDIT VSA — extension σ-bands (P3) à confluence M5.
        # AVANT : (slope * sign) > 0 — pente minime considérée comme extension.
        # CORRECTION : on exige |slope| > sigma_threshold pour éviter faux signaux
        # sur série à variance faible. sigma_threshold = 1.0 (P9 audit : pente
        # < 1.0 = bruit, pas une vraie extension).
        sigma_threshold = 1.0
        m5_ok = (
            abs(slope) >= sigma_threshold
            and (slope * (1 if direction == "BUY" else -1)) > 0
        )

    # 4. Cinématique M15 ALLOW
    forces, prices = [], []
    for j in range(max(0, len(bars_m15) - 60), len(bars_m15)):
        b = bars_m15[j]
        if int(b["bar_time"]) <= bar_time:
            forces.append(_delta_at(b, symbol))
            prices.append(float(b["close"]))
    m15_cine_ok = False
    m15_cine_detail = {}
    if len(forces) >= 10:
        pip = 0.01 if symbol.endswith("JPY") else 0.0001
        ana = analyze_series(forces, prices, label=f"{symbol} M15", pip_size=pip)
        verdict = cinematics_verdict(ana, direction)
        m15_cine_ok = verdict["action"] == "ALLOW"
        m15_cine_detail = {
            "action": verdict["action"], "reasons": verdict["reasons"],
            "pic": ana.get("force_pic"), "last_force": ana.get("last_force"),
            "slope": ana.get("slope_force_5"), "accel": ana.get("acceleration_force"),
        }

    score = sum([m30_ok, h1_ok, m5_ok, m15_cine_ok])
    # Sizing : 0.5 (confluence faible) → 1.0 (confluence totale)
    sizing_multiplier = 0.5 + 0.5 * (score / 4.0)

    return {
        "score": score,
        "max_score": 4,
        "components": {
            "m30": m30_ok, "h1": h1_ok, "m5": m5_ok, "m15_cine": m15_cine_ok,
        },
        "detail": {
            "d_m30": round(d_m30, 2) if d_m30 is not None else None,
            "d_h1": round(d_h1, 2) if d_h1 is not None else None,
            "m5": m5_ana if m5_avail else {"available": False},
            "m15_cine": m15_cine_detail,
        },
        "sizing_multiplier": round(sizing_multiplier, 3),
    }

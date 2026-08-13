"""v10_edge_overlap_filter.py — Filtre de sélection edge OVERLAP (Option C).

Implémente la décision stratégique DECISION_OVERLAP_VS_SCAN_LARGE.md (Option C) :
  - Couche EXÉCUTION : uniquement les signaux edge OVERLAP prouvé
    (fenêtre 12-16 UTC + |delta_forces|≥25, paires EURUSD/USDCHF/AUDUSD,
    config optimisée 13/08 : TP=2xATR, SL=1xATR, hold 4).
  - Couche EXPLORATION : tout le reste est taggé `exploration_only` (SHADOW,
    jamais exécutable) — on continue d'apprendre sans risquer le capital.

Le filtre est ADDITIF (R2) : il ne modifie aucune décision existante, il
ajoute un tag `edge_overlap` + `execution_eligible` consommé par la couche
d'exécution (paper/live). R6 fail-open : données insuffisantes → pas de tag.

R10 : ce module ne passe JAMAIS d'ordre. Il produit un verdict de sélection.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Optional

# Config edge OVERLAP optimisée (benchmark 13/08)
EDGE_PAIRS = ("EURUSD", "USDCHF", "AUDUSD")
EDGE_TF = "M15"
EDGE_DELTA_MIN = 25.0
EDGE_HOUR_START = 12
EDGE_HOUR_END = 16
WARMUP_BARS = 60


def _delta_forces(b: dict, pair: str) -> float:
    base, quote = pair[:3], pair[3:6]
    return float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0))


def edge_overlap_verdict(
    db_path: Path | str,
    symbol: str,
    timeframe: str,
    bar_time: Optional[int] = None,
) -> dict:
    """Verdict de sélection pour un (symbol, timeframe, bar_time).

    Retourne :
      {"edge_overlap": bool, "execution_eligible": bool,
       "exploration_only": bool, "reason": str, "delta": float|None}

    - edge_overlap=True si le tick est dans la fenêtre OVERLAP, sur une paire
      porteuse, avec |delta_forces|≥25 (config optimisée).
    - execution_eligible = edge_overlap ET timeframe M15 (l'edge est M15).
    - exploration_only = tout le reste (SHADOW, jamais exécutable).
    """
    if symbol not in EDGE_PAIRS:
        return {"edge_overlap": False, "execution_eligible": False,
                "exploration_only": True, "reason": "pair_not_carry", "delta": None}

    # Barre la plus récente si bar_time non fourni
    if bar_time is None:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT bar_time FROM forces_snapshots WHERE symbol=? AND timeframe=? "
                "AND is_closed_bar=1 ORDER BY bar_time DESC LIMIT 1",
                (symbol, timeframe),
            ).fetchone()
            bar_time = int(row[0]) if row else None
        finally:
            con.close()
        if bar_time is None:
            return {"edge_overlap": False, "execution_eligible": False,
                    "exploration_only": True, "reason": "no_bars", "delta": None}

    hour = dt.datetime.fromtimestamp(int(bar_time), tz=dt.UTC).hour
    if not (EDGE_HOUR_START <= hour < EDGE_HOUR_END):
        return {"edge_overlap": False, "execution_eligible": False,
                "exploration_only": True, "reason": "not_overlap", "delta": None}

    # Delta forces sur la barre M15 (l'edge est défini sur M15)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT force_eur, force_usd, force_gbp, force_jpy, force_cad, force_chf, "
            "force_aud, force_nzd FROM forces_snapshots WHERE symbol=? AND timeframe=? "
            "AND bar_time=? LIMIT 1",
            (symbol, EDGE_TF, bar_time),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return {"edge_overlap": False, "execution_eligible": False,
                "exploration_only": True, "reason": "no_m15_bar", "delta": None}

    b = dict(zip(("force_eur", "force_usd", "force_gbp", "force_jpy",
                   "force_cad", "force_chf", "force_aud", "force_nzd"), row))
    d = _delta_forces(b, symbol)
    if abs(d) < EDGE_DELTA_MIN:
        return {"edge_overlap": False, "execution_eligible": False,
                "exploration_only": True, "reason": "delta_too_small", "delta": round(d, 2)}

    # Filtre cinématique (Søn) : exhaustion/divergence → pas exécutable
    # (même logique que le runner — la cinématique est la gate de qualité)
    cinematics = {"blocked": False, "reasons": []}
    try:
        from .v10_cinematics import load_force_price_series, analyze_series, cinematics_verdict
        forces, prices, _bt = load_force_price_series(db_path, symbol, EDGE_TF, limit=120)
        pip = 0.01 if symbol.endswith("JPY") else 0.0001
        ana = analyze_series(forces, prices, label=f"{symbol} M15", pip_size=pip)
        verdict = cinematics_verdict(ana, "BUY" if d > 0 else "SELL")
        if verdict["action"] == "BLOCK":
            cinematics = {"blocked": True, "reasons": verdict["reasons"]}
        else:
            cinematics = {"blocked": False, "reasons": [], "analysis": {
                k: v for k, v in ana.items() if k != "divergence_detail"}}
    except Exception:
        pass  # R6 fail-open : cinématique indisponible → laisse passer

    return {
        "edge_overlap": True,
        "execution_eligible": timeframe == EDGE_TF and not cinematics["blocked"],
        "exploration_only": False,
        "reason": "edge_overlap_confirmed",
        "delta": round(d, 2),
        "direction": "BUY" if d > 0 else "SELL",
        "cinematics": cinematics,
    }

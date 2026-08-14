"""v10_quality_score.py — Le score de qualité institutionnel (Søn 13/08).

PARADIGME : le système est un CHASSEUR, pas un notaire.
Il ne bloque pas (BLOCK) — il ÉVALUE (score 0-10) et agit selon la qualité.

Søn : "ne m'enferme pas dans un laboratoire stérile... trouve les choses
exploitables, la qualité... pas de friction... le système doit être plus
vif, plus juste, plus prompt à exploiter — pas plus lent."

Le score agrège 5 dimensions (les piliers déjà codés) :
  📊 Pilier 7 — Forces dans les zones (0-3)    [calibration percentile]
  📈 Pilier 1 — Cinématique (-2 à +2)           [v10_cinematics]
  🔗 Pilier 2 — Confluence TF (0-2)             [v10_confluence_tf]
  🔄 Pilier 6 — Phase du cycle (-2 à +2)        [à coder — placeholder neutre]
  🌐 Pilier 3 — Coalition (0-1)                 [à coder — placeholder neutre]

Verdict instantané (pas de gate, pas d'attente) :
  ≥ 7  → 🟢 EXPLOITABLE — sizing renforcé (×1.0-1.5)
  4-6  → 🟡 À SURVEILLER — sizing réduit (×0.5-0.8)
  < 4  → 🔴 BRUIT — ignorer (×0)

R10 : compute only, zéro ordre réel. R6 fail-open partout.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from .v10_cinematics import analyze_series, cinematics_verdict
from .v10_forces_par_tf import calibrer_zones_tf


def _zone_score(value: float, zones: Dict) -> int:
    """Score 0-3 selon la position de la force dans les zones de SON TF."""
    p10, p25, p75, p90 = zones["p10"], zones["p25"], zones["p75"], zones["p90"]
    if value <= p10 or value >= p90:
        return 3  # zone dynamique extrême
    if value <= p25 or value >= p75:
        return 2  # zone haute/basse
    # mouvement vers la zone (pente positive pour BUY, négative pour SELL)
    return 1  # zone moyenne — en mouvement


def _cinematics_score(analysis: Dict, direction: str) -> int:
    """Score -2 à +2 selon la cinématique de la force.

    Remplace le BLOCK binaire par un score continu :
      -2 : exhaustion (pic → retombée) — autrefois BLOCK
      -2 : divergence (force ≠ prix) — autrefois BLOCK
      +1 : extension saine (pente positive dans le sens du trade)
      +2 : accélération favorable
       0 : neutre
    """
    if analysis.get("error"):
        return 0  # R6 fail-open
    reasons = analysis
    score = 0
    # Pénalités (anciens BLOCK)
    if analysis.get("divergence_force_price"):
        score -= 2
    if analysis.get("exhaustion_pic"):
        score -= 2
    # Bonus
    slope = analysis.get("slope_force_5", 0)
    accel = analysis.get("acceleration_force", 0)
    dir_mult = 1 if direction == "BUY" else -1
    if slope * dir_mult > 2:
        score += 1  # extension saine
    if accel * dir_mult > 3:
        score += 1  # accélération
    return max(-4, min(2, score))


def _confluence_score_raw(conf: Dict) -> int:
    """Score 0-2 selon la confluence TF (depuis v10_confluence_tf)."""
    if conf.get("error"):
        return 0  # R6 fail-open
    raw = conf.get("score", 0)
    if raw >= 4:
        return 2
    if raw >= 3:
        return 1
    if raw >= 2:
        return 0
    return -1  # conflit majoritaire


def quality_score(
    db_path: str,
    symbol: str,
    bar_time: int,
    direction: str,
    bars_m15: List[dict],
    bars_m5: Optional[List[dict]] = None,
    bars_m30: Optional[List[dict]] = None,
    bars_h1: Optional[List[dict]] = None,
) -> Dict:
    """Score de qualité institutionnel [0-10] pour un signal.

    Args:
        db_path    : chemin DB
        symbol     : paire (EURUSD, USDCHF, AUDUSD)
        bar_time   : timestamp de la barre M15 du signal
        direction  : BUY / SELL
        bars_m15   : barres M15 (pour cinématique)
        bars_m5/m30/h1 : barres des autres TF (optionnel)

    Retourne : {score, max_score, verdict, sizing_multiplier,
                components: {zones, cinematics, confluence, cycle, coalition},
                detail: {...}}
    """
    base, quote = symbol[:3], symbol[3:6]
    pip = 0.01 if symbol.endswith("JPY") else 0.0001
    detail = {}

    # ── Pilier 7 : Forces dans les zones (0-3) ──────────────────────────────
    try:
        zones_calib = calibrer_zones_tf(db_path, symbol, "M15", f"force_{base.lower()}")
        # Valeur actuelle de la force base sur M15
        cur_force = None
        for b in reversed(bars_m15):
            if int(b["bar_time"]) <= bar_time:
                cur_force = float(b.get(f"force_{base.lower()}", 0.0))
                break
        if cur_force is not None and "zones" in zones_calib:
            z_score = _zone_score(cur_force, zones_calib["zones"])
            detail["zones"] = {"force": round(cur_force, 1), "zones": zones_calib["zones"], "score": z_score}
        else:
            z_score = 0
            detail["zones"] = {"error": "no_data"}
    except Exception:
        z_score = 0
        detail["zones"] = {"error": "fail_open"}

    # ── Pilier 1 : Cinématique (-4 à +2) ────────────────────────────────────
    try:
        forces, prices = [], []
        for j in range(max(0, len(bars_m15) - 60), len(bars_m15)):
            b = bars_m15[j]
            # P8 AUDIT VSA — extension end-of-bar gate (P5) à quality_score.
            # AVANT : int(b["bar_time"]) <= bar_time — suppose implicitement
            # bougie fermée. Si bars_m15 contient la bougie en formation
            # (is_closed_bar=0), on calcule cinématique sur Bougie en formation.
            # CORRECTION : on filtre explicitement is_closed_bar (défaut 1 si absent).
            if int(b["bar_time"]) <= bar_time and b.get("is_closed_bar", 1):
                forces.append(float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0)))
                prices.append(float(b["close"]))
        if len(forces) >= 10:
            ana = analyze_series(forces, prices, label=f"{symbol} M15", pip_size=pip)
            c_score = _cinematics_score(ana, direction)
            detail["cinematics"] = {
                "score": c_score,
                "pic": ana.get("force_pic"), "last_force": ana.get("last_force"),
                "slope": ana.get("slope_force_5"), "accel": ana.get("acceleration_force"),
                "divergence": ana.get("divergence_force_price"),
                "exhaustion": ana.get("exhaustion_pic"),
            }
        else:
            c_score = 0
            detail["cinematics"] = {"error": "insufficient"}
    except Exception:
        c_score = 0
        detail["cinematics"] = {"error": "fail_open"}

    # ── Pilier 2 : Confluence TF (-1 à +2) ──────────────────────────────────
    try:
        from .v10_confluence_tf import confluence_score as _cs
        conf = _cs(db_path, symbol, bar_time, direction,
                   bars_m15=bars_m15, bars_m5=bars_m5,
                   bars_m30=bars_m30, bars_h1=bars_h1)
        conf_score = _confluence_score_raw(conf)
        detail["confluence"] = {
            "score": conf_score, "raw": conf.get("score", 0),
            "components": conf.get("components", {}),
            "sizing": conf.get("sizing_multiplier", 0.75),
        }
    except Exception:
        conf_score = 0
        detail["confluence"] = {"error": "fail_open"}

    # ── Pilier 6 : Phase du cycle (placeholder neutre, à coder) ─────────────
    cycle_score = 0  # neutre tant que le Pilier 6 n'est pas validé
    detail["cycle"] = {"score": cycle_score, "note": "Pilier 6 non validé — brainstorming en cours"}

    # ── Pilier 3 : Coalition (placeholder neutre, à coder) ──────────────────
    coalition_score = 0  # neutre tant que le Pilier 3 n'est pas validé
    detail["coalition"] = {"score": coalition_score, "note": "Pilier 3 non validé — brainstorming en cours"}

    # ── Score total (0-10) ──────────────────────────────────────────────────
    # Normalisation : z(0-3) + c(-4..2) + conf(-1..2) + cycle(0) + coalition(0)
    # Plage théorique : -5 à 7. On ramène à 0-10.
    raw = z_score + c_score + conf_score + cycle_score + coalition_score
    # raw ∈ [-5, 7] → score ∈ [0, 10]
    score = max(0, min(10, round((raw + 5) / 12 * 10)))

    # Verdict instantané (pas de gate)
    if score >= 7:
        verdict = "EXPLOITABLE"
        sizing = 1.0 + 0.5 * (score - 7) / 3  # 1.0 → 1.5
    elif score >= 4:
        verdict = "SURVEILLER"
        sizing = 0.5 + 0.3 * (score - 4) / 3  # 0.5 → 0.8
    else:
        verdict = "BRUIT"
        sizing = 0.0

    return {
        "score": score,
        "max_score": 10,
        "verdict": verdict,
        "sizing_multiplier": round(sizing, 3),
        "raw_score": raw,
        "components": {
            "zones": z_score,
            "cinematics": c_score,
            "confluence": conf_score,
            "cycle": cycle_score,
            "coalition": coalition_score,
        },
        "detail": detail,
    }
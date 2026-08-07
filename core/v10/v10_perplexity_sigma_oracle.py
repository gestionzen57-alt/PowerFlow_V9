# Perplexity Contribution — Sigma Oracle v1.0 — 2026-08-07
# Intégré Sprint 14 — PowerFlow_V9 feat/v9-foundation-clean
# Classifie la zone grise sigma [12,28] en 3 sous-états distincts :
# COILING (compression), RESOLVING (résolution), RANGING (noise)

from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Enums & Dataclasses
# ─────────────────────────────────────────────────────────────────────

class SigmaSubState(str, Enum):
    """Sous-états de la zone grise sigma [12,28]."""
    COILING = "COILING"      # compression pré-explosion
    RESOLVING = "RESOLVING"  # résolution en cours
    RANGING = "RANGING"      # noise pur, mid-range stable


@dataclass
class SigmaOracleResult:
    """Résultat de l'oracle sigma."""
    sub_state: SigmaSubState
    action: str                    # WAIT_PRIME / WAIT / WATCH
    confidence: float              # 0.0 → 1.0
    rationale: str                 # log humain lisible
    ob_alert: bool                 # alerte OB/BOS
    sigma_current: float
    sigma_slope: float
    n_points: int

    def as_dict(self) -> dict:
        return {
            "sub_state": self.sub_state.value,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "rationale": self.rationale,
            "ob_alert": self.ob_alert,
            "sigma_current": round(self.sigma_current, 3),
            "sigma_slope": round(self.sigma_slope, 4),
            "n_points": self.n_points,
        }


# ─────────────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    "coiling_slope_threshold": -0.8,
    "resolving_slope_threshold": 0.8,
    "coiling_sigma_max": 22.0,
    "resolving_sigma_min": 20.0,
}

def load_sigma_oracle_config(config_path: str = "config/v10_active_thresholds.json") -> dict:
    """Charge la config sigma_oracle depuis le fichier JSON global."""
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        return data.get("sigma_oracle", DEFAULT_THRESHOLDS)
    except Exception as e:
        log.warning("Config sigma_oracle non trouvée, utilisation défauts: %s", e)
        return DEFAULT_THRESHOLDS


# ─────────────────────────────────────────────────────────────────────
# Core Logic
# ─────────────────────────────────────────────────────────────────────

def _compute_slope(values: List[float]) -> float:
    """Pente linéaire simple sur les dernières valeurs (régression OLS)."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    num = sum((x - mx) * (v - my) for x, v in zip(xs, values))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den != 0 else 0.0


def sigma_oracle(
    *,
    sigma_history: List[float],
    ob_proximity: bool = False,
    bos_confirmed: bool = False,
    config_path: str = "config/v10_active_thresholds.json",
) -> SigmaOracleResult:
    """
    Classifie la zone grise sigma [12,28] en 3 sous-états.

    Args:
        sigma_history: historique sigma (derniers 5 points min, plus = meilleur)
        ob_proximity: True si prix près d'un Order Block (SMC context)
        bos_confirmed: True si BOS récent confirmé (SMC context)
        config_path: chemin vers config JSON

    Returns:
        SigmaOracleResult avec sub_state, action, confidence, rationale, ob_alert
    """
    cfg = load_sigma_oracle_config(config_path)

    if not sigma_history:
        return SigmaOracleResult(
            sub_state=SigmaSubState.RANGING,
            action="WAIT",
            confidence=0.40,
            rationale="Pas d'historique sigma → fallback RANGING",
            ob_alert=False,
            sigma_current=0.0,
            sigma_slope=0.0,
            n_points=0,
        )

    sigma_current = sigma_history[-1]
    n_points = len(sigma_history)

    # Seuil minimum de points pour décision fiable
    if n_points < 3:
        return SigmaOracleResult(
            sub_state=SigmaSubState.RANGING,
            action="WAIT",
            confidence=0.40,
            rationale=f"Historique insuffisant ({n_points} pts) → fallback RANGING",
            ob_alert=False,
            sigma_current=sigma_current,
            sigma_slope=0.0,
            n_points=n_points,
        )

    # Calcul pente sur fenêtre (max 5 points comme spécifié)
    window = min(5, n_points)
    slope = _compute_slope(sigma_history[-window:])

    coiling_slope_thr = cfg.get("coiling_slope_threshold", -0.8)
    resolving_slope_thr = cfg.get("resolving_slope_threshold", 0.8)
    coiling_sigma_max = cfg.get("coiling_sigma_max", 22.0)
    resolving_sigma_min = cfg.get("resolving_sigma_min", 20.0)

    # ─────────────────────────────────────────────────────────────
    # COILING : compression (slope négatif fort, sigma bas dans la zone)
    # ─────────────────────────────────────────────────────────────
    if slope < coiling_slope_thr and sigma_current < coiling_sigma_max:
        ob_alert = ob_proximity
        ob_msg = "OB proximity -> alerte" if ob_alert else "Pas d'OB proximity"
        rationale = (
            f"COILING détecté : slope={slope:.3f} < {coiling_slope_thr}, "
            f"sigma={sigma_current:.1f} < {coiling_sigma_max}. "
            f"Compression pré-explosion. "
            f"{ob_msg}."
        )
        return SigmaOracleResult(
            sub_state=SigmaSubState.COILING,
            action="WAIT_PRIME",
            confidence=0.75,
            rationale=rationale,
            ob_alert=ob_alert,
            sigma_current=sigma_current,
            sigma_slope=slope,
            n_points=n_points,
        )

    # ─────────────────────────────────────────────────────────────
    # RESOLVING : résolution (slope positif fort, sigma haut dans la zone)
    # ─────────────────────────────────────────────────────────────
    if slope > resolving_slope_thr and sigma_current > resolving_sigma_min:
        ob_alert = bos_confirmed
        bos_msg = "BOS confirmed -> alerte" if ob_alert else "Pas de BOS confirmé"
        rationale = (
            f"RESOLVING détecté : slope={slope:.3f} > {resolving_slope_thr}, "
            f"sigma={sigma_current:.1f} > {resolving_sigma_min}. "
            f"Résolution en cours. "
            f"{bos_msg}."
        )
        return SigmaOracleResult(
            sub_state=SigmaSubState.RESOLVING,
            action="WATCH",
            confidence=0.65,
            rationale=rationale,
            ob_alert=ob_alert,
            sigma_current=sigma_current,
            sigma_slope=slope,
            n_points=n_points,
        )

    # ─────────────────────────────────────────────────────────────
    # RANGING : noise pur mid-range stable
    # ─────────────────────────────────────────────────────────────
    rationale = (
        f"RANGING : slope={slope:.3f} stable (ni COILING ni RESOLVING), "
        f"sigma={sigma_current:.1f} mid-range. Noise pur."
    )
    return SigmaOracleResult(
        sub_state=SigmaSubState.RANGING,
        action="WAIT",
        confidence=0.40,
        rationale=rationale,
        ob_alert=False,
        sigma_current=sigma_current,
        sigma_slope=slope,
        n_points=n_points,
    )


# ─────────────────────────────────────────────────────────────────────
# Helper pour intégration dans fatboy_gate / orchestrateur
# ─────────────────────────────────────────────────────────────────────

def get_sigma_history(
    pair: str,
    timeframe: str,
    n: int = 5,
    db_path: str = "data/v9_forces.db",
) -> List[float]:
    """
    Récupère l'historique sigma pour (pair, timeframe) depuis forces_snapshots.

    Calcule sigma sur les 8 devises pour chaque barre fermée.
    """
    import sqlite3
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    try:
        rows = cur.execute(
            """
            SELECT force_eur, force_usd, force_gbp, force_jpy,
                   force_cad, force_chf, force_aud, force_nzd
            FROM forces_snapshots
            WHERE symbol=? AND timeframe=? AND is_closed_bar=1
            ORDER BY bar_time DESC LIMIT ?
            """,
            (pair, timeframe, n),
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return []

    sigmas = []
    for row in reversed(rows):  # chronologique
        forces = [row[i] for i in range(8)]
        if all(v is not None for v in forces):
            mean_f = sum(forces) / 8
            var = sum((v - mean_f) ** 2 for v in forces) / 8
            sigma = var ** 0.5
            sigmas.append(sigma)

    return sigmas


def apply_sigma_oracle_to_level(
    current_level: str,
    oracle: SigmaOracleResult,
) -> str:
    """
    Applique l'action de l'oracle au niveau de signal.

    Logique Option C Hybrid :
      - WAIT_PRIME (COILING)  → forcer A2 (ne pas tomber NONE)
      - WATCH (RESOLVING)     → garder niveau courant (A1/A2), pas de downgrade
      - WAIT (RANGING)        → laisser NONE standard
    """
    if oracle.action == "WAIT_PRIME":
        return "A2" if current_level in ("A1", "A2", "A3") else current_level
    elif oracle.action == "WATCH":
        return current_level  # garde A1 ou A2, ne downgrade pas
    else:
        return "NONE"  # RANGING → comportement Fatboy standard


__all__ = [
    "SigmaSubState",
    "SigmaOracleResult",
    "sigma_oracle",
    "get_sigma_history",
    "apply_sigma_oracle_to_level",
    "load_sigma_oracle_config",
    "DEFAULT_THRESHOLDS",
]
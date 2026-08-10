"""V10 Stale Guard — filtre de fraîcheur par (paire, TF) (R2 additif pur).

Chantier 1 / HERMES_PROMPT_MAX_V2 (Perplexity CEO 10/08 10:23 CEST).

Détecte si un combo (symbol, timeframe) est stale (données trop anciennes)
et bloque la décision en retournant signal_level='NONE' (stale_blocked).

Adapté au schéma réel de `data/v9_forces.db` :
  - colonne `symbol` (pas `pair`)
  - colonne `bar_time` = epoch int (secondes)
  - colonne `timestamp` = ISO string

Doctrine : R2 additif pur (nouveau fichier, 0 modification module existant),
R6 fail-open (erreur DB → is_stale=False, laisser passer), R9 audit, R10 zéro ordre.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Dict, Optional

# Seuils de fraîcheur par TF (minutes). Un combo dont le lag dépasse le seuil
# est considéré stale → signal bloqué.
STALE_THRESHOLDS: Dict[str, int] = {
    "M1": 15, "M5": 30, "M15": 60, "M30": 90, "H1": 240, "H4": 480, "D1": 1440,
}
DEFAULT_THRESHOLD_MIN = 90


@dataclass
class StaleCheckResult:
    pair: str
    tf: str
    lag_minutes: float
    is_stale: bool
    threshold: int
    last_bar: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "pair": self.pair, "tf": self.tf,
            "lag_minutes": round(self.lag_minutes, 1),
            "is_stale": self.is_stale, "threshold": self.threshold,
            "last_bar": self.last_bar,
        }


def _now_epoch() -> float:
    return time.time()


def check_stale(db_path: str, pair: str, tf: str) -> StaleCheckResult:
    """Vérifie la fraîcheur d'un combo (symbol, timeframe).

    R6 fail-open : si erreur DB ou colonne absente → is_stale=False (laisser
    passer, ne pas bloquer à tort). Si aucun barre → is_stale=True (pas de
    données = stale).
    """
    threshold = STALE_THRESHOLDS.get(tf, DEFAULT_THRESHOLD_MIN)
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        row = conn.execute(
            "SELECT MAX(bar_time) FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=?",
            (pair, tf),
        ).fetchone()
        conn.close()
        if not row or row[0] is None:
            return StaleCheckResult(pair, tf, 9999.0, True, threshold, None)
        last_bar_epoch = float(row[0])
        lag_min = (time.time() - last_bar_epoch) / 60.0
        return StaleCheckResult(
            pair, tf, round(lag_min, 1), lag_min > threshold, threshold,
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(last_bar_epoch)),
        )
    except Exception:
        # R6 fail-open : ne pas bloquer sur erreur DB
        return StaleCheckResult(pair, tf, 0.0, False, threshold, None)


def is_combo_fresh(db_path: str, pair: str, tf: str) -> bool:
    """True si le combo est frais (non stale)."""
    return not check_stale(db_path, pair, tf).is_stale


def stale_blocked_signal(db_path: str, pair: str, tf: str) -> dict:
    """Retourne un signal 'NONE' bloqué si stale, sinon None.

    Usage : dans le pipeline de décision, si le résultat n'est pas None,
    remplacer le signal par signal_level='NONE' + reason='stale_blocked'.
    """
    res = check_stale(db_path, pair, tf)
    if res.is_stale:
        return {
            "signal_level": "NONE",
            "reason": "stale_blocked",
            "stale": res.as_dict(),
        }
    return None

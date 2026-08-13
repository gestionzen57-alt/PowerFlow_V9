"""v10_forces_par_tf.py — SQUELETTE Pilier 7 (forces par timeframe).

⚠️ MÉTHODOLOGIE (docs/V10/METHODOLOGIE_INJECTION.md) :
CE MODULE EST VIDE VOLONTAIREMENT (sauf calibration percentile, qui est un
calcul statistique pur sans interprétation — autorisé par la méthodologie).
Les règles de lecture (croisement + zones extrêmes + double test de rejet
+ propagation/répulsion) sont la propriété de Søn — à injecter après
validation du Pilier 7.

Blocs source : docs/V10/LECTURE_FORCES_PAR_TIMEFRAME.md (R1-R5)

Règles en attente :
  - R1 Calibration par TF (percentile) — ⚠️ CALCUL STATISTIQUE PUR, OK
  - R2 Lecture par TF (valeur dans les zones de SON TF) — à implémenter
  - R3 Croisement M5 + zones extrêmes M15/M30 — à implémenter
  - R4 Double test de rejet de prix — à implémenter
  - R5 Propagation vs Répulsion — à implémenter

Statut : 🔶 Calibration OK (statistique), règles R2-R5 en attente.

R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List


# ── R1 : CALIBRATION PAR TF (percentile) — calcul statistique pur ──────────
# Autorisé par la méthodologie : pas d'interprétation comportementale,
# juste la distribution des valeurs de force par TF.

def calibrer_zones_tf(
    db_path: str,
    symbol: str,
    tf: str,
    force_col: str,
    n_bars: int = 2000,
) -> Dict:
    """Calibre les zones (basse/moyenne/haute/extrême) par percentile.

    Retourne : {tf, symbol, force_col, zones: {p10, p25, p75, p90},
                n_samples, computed_at}
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = con.execute(
        f"SELECT {force_col} FROM forces_snapshots "
        "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (symbol, tf, n_bars),
    ).fetchall()
    con.close()
    vals = sorted(float(r[0]) for r in rows)
    if not vals:
        return {"tf": tf, "symbol": symbol, "force_col": force_col, "error": "no_data"}

    def pct(p):
        idx = min(len(vals) - 1, int(p * len(vals)))
        return round(vals[idx], 1)

    return {
        "tf": tf, "symbol": symbol, "force_col": force_col,
        "zones": {"p10": pct(0.10), "p25": pct(0.25), "p75": pct(0.75), "p90": pct(0.90)},
        "n_samples": len(vals),
    }


# ── R2-R5 : RÈGLES DE LECTURE (propriété Søn, à implémenter après validation) ─

def lire_force_dans_zone(calib: Dict, valeur: float) -> Dict:
    """R2 : lit une valeur dans les zones de SON TF (à implémenter)."""
    raise NotImplementedError("Pilier 7 R2 non validé — brainstorming en cours")


def croisement_zones_extremes(db_path: str, symbol: str) -> Dict:
    """R3 : croisement M5 + zones extrêmes M15/M30 (à implémenter)."""
    raise NotImplementedError("Pilier 7 R3 non validé — brainstorming en cours")


def double_test_rejet(db_path: str, symbol: str) -> Dict:
    """R4 : double test de rejet de prix (à implémenter)."""
    raise NotImplementedError("Pilier 7 R4 non validé — brainstorming en cours")


def propagation_repulsion(db_path: str, symbol: str) -> Dict:
    """R5 : propagation vs répulsion après croisement (à implémenter)."""
    raise NotImplementedError("Pilier 7 R5 non validé — brainstorming en cours")

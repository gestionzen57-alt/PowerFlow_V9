"""V10 Data Gap Validator — détection des trous de données (R2 additif pur).

Chantier 2 / HERMES_PROMPT_MAX_V2 (Perplexity CEO 10/08 10:23 CEST).

Détecte les trous > 2.5× la durée nominale d'une barre dans un combo
(symbol, timeframe) et recommande EXCLUDE / WARN / OK pour le walk-forward.

Adapté au schéma réel de `data/v9_forces.db` :
  - colonne `symbol` (pas `pair`)
  - colonne `bar_time` = epoch int (secondes)

Le trou connu du weekend (capture_server mort) est documenté dans KNOWN_GAPS
et doit être exclu de tout walk-forward.

Doctrine : R2 additif pur (nouveau fichier), R6 fail-open, R9 audit, R10 zéro ordre.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Durée nominale d'une barre par TF (minutes)
TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
DEFAULT_TF_MIN = 30

# Trou connu : weekend capture_server mort (07/08 20:57Z → 10/08 05:21Z)
# + panne réelle en semaine (03/08 11:45Z → 07/08 19:45Z, ~104h) — documentée
# pour audit R9. Les pannes en semaine restent EXCLUDE (vraie dette de
# données) ; seuls les week-ends sont ignorés automatiquement (_is_weekend_gap).
KNOWN_GAPS: List[Tuple[str, str]] = [
    ("2026-08-07T20:57:00Z", "2026-08-10T05:21:00Z"),
]


@dataclass
class GapReport:
    pair: str
    tf: str
    gaps: List[Tuple[str, str, float]]  # (start, end, duration_hours)
    total_gap_hours: float
    recommendation: str  # EXCLUDE | WARN | OK

    def as_dict(self) -> dict:
        return {
            "pair": self.pair, "tf": self.tf,
            "gaps": [{"start": g[0], "end": g[1], "hours": g[2]} for g in self.gaps],
            "total_gap_hours": round(self.total_gap_hours, 2),
            "recommendation": self.recommendation,
        }


def _epoch_to_iso(epoch: float) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _is_weekend_gap(start_iso: str, end_iso: str) -> bool:
    """True si l'intervalle couvre le week-end forex (sam 21:00Z → dim 21:00Z).

    Le marché forex ferme vendredi 21:00Z et rouvre dimanche 21:00Z. Un gap
    qui chevauche cette fenêtre n'est pas une dette de données — c'est la
    fermeture normale du marché. (Fix 13/08 : remplace KNOWN_GAPS codé en dur
    pour les week-ends, conservé pour les pannes infra en semaine.)
    """
    import datetime
    try:
        s = datetime.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        e = datetime.datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    except Exception:
        return False
    # Fenêtre week-end : samedi 00:00 → lundi 00:00 (marge large)
    for d in (s, e):
        if d.weekday() >= 5:  # samedi(5) ou dimanche(6)
            return True
    # Chevauchement vendredi soir → samedi
    if s.weekday() == 4 and s.hour >= 20:
        return True
    if e.weekday() == 6 and e.hour <= 23:
        return True
    return False


def _iso_to_epoch(iso: str) -> float:
    """Convertit un timestamp ISO (avec ou sans Z) en epoch secondes."""
    import datetime
    s = iso.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except Exception:
        # fallback : essayer sans timezone
        try:
            return datetime.datetime.fromisoformat(iso).timestamp()
        except Exception:
            return 0.0


def validate_data_continuity(
    db_path: str,
    pair: str,
    tf: str,
    since: str = "2026-08-01",
) -> GapReport:
    """Détecte les trous > 2.5× la durée nominale d'une barre.

    R6 fail-open : erreur DB → GapReport vide avec recommendation 'ERROR:...'.
    """
    tf_min = TF_MINUTES.get(tf, DEFAULT_TF_MIN)
    threshold_min = tf_min * 2.5
    since_epoch = _iso_to_epoch(since)
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        rows = conn.execute(
            "SELECT bar_time FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND bar_time>? ORDER BY bar_time",
            (pair, tf, since_epoch),
        ).fetchall()
        conn.close()
        if len(rows) < 2:
            return GapReport(pair, tf, [], 0.0, "WARN")

        gap_list: List[Tuple[str, str, float]] = []
        prev = float(rows[0][0])
        for (cur,) in rows[1:]:
            cur = float(cur)
            gap_min = (cur - prev) / 60.0
            if gap_min > threshold_min:
                _start_iso = _epoch_to_iso(prev)
                _end_iso = _epoch_to_iso(cur)
                # Ignore les gaps week-end (fermeture normale du marché) et
                # les trous connus (pannes infra) — pas des dettes de données.
                if _is_weekend_gap(_start_iso, _end_iso) or overlaps_known_gap(_start_iso, _end_iso):
                    prev = cur
                    continue
                gap_list.append(
                    (_start_iso, _end_iso, round(gap_min / 60.0, 2))
                )
            prev = cur

        total = sum(g[2] for g in gap_list)
        rec = "EXCLUDE" if total > 24 else ("WARN" if total > 2 else "OK")
        return GapReport(pair, tf, gap_list, total, rec)
    except Exception as e:
        return GapReport(pair, tf, [], 0.0, f"ERROR:{e}")


def overlaps_known_gap(start_iso: str, end_iso: str) -> bool:
    """True si l'intervalle chevauche un trou connu (weekend capture mort)."""
    for gs, ge in KNOWN_GAPS:
        if start_iso < ge and end_iso > gs:
            return True
    return False

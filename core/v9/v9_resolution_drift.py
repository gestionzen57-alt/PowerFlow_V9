"""v9_resolution_drift.py — Détecteur de divergence de résolution (réconciliation 2026-07-20).

**Pourquoi ce module existe**
Deux moteurs comptent la performance : `decisions` (DYNAMIC) et `paper_trades`
(résolution héritée). L'audit du 2026-07-20 a mesuré un désaccord miroir (WR
87.3% vs 23.8%). Ce module **mesure** cette divergence en continu et
**recommande** une alerte — il ne mute rien (R30 : recommande, n'applique pas).

**Contrat**
`compute_resolution_drift(db_path)` calcule le WR sur les 100 derniers
`paper_trades` clôturés ET les 100 dernières `decisions` résolues, et retourne
`ResolutionDrift(wr_paper_trades, wr_decisions, drift_pct, alert_level)`.

Seuils :
  - drift_pct > 40 → CRITICAL (boucle R30 cassée : les deux moteurs se contredisent)
  - drift_pct > 20 → WARN
  - sinon         → none

Défensif (R6) : lecture seule stricte, jamais de crash. Table vide → WR None,
drift None, alerte none (pas de faux positif sur un système froid).
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_WINDOW = 100
WARN_THRESHOLD = 20.0
CRITICAL_THRESHOLD = 40.0


@dataclass(frozen=True)
class ResolutionDrift:
    """Verdict de divergence entre les deux moteurs de résolution."""
    wr_paper_trades: Optional[float]  # 0-1, None si pas de données
    wr_decisions: Optional[float]     # 0-1, None si pas de données
    drift_pct: Optional[float]        # |wr_dec - wr_pt| × 100, None si indéterminable
    n_paper_trades: int
    n_decisions: int
    alert_level: str = "none"         # "none" | "WARN" | "CRITICAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "wr_paper_trades": self.wr_paper_trades,
            "wr_decisions": self.wr_decisions,
            "drift_pct": self.drift_pct,
            "n_paper_trades": self.n_paper_trades,
            "n_decisions": self.n_decisions,
            "alert_level": self.alert_level,
        }


def _connect_ro(db_path: Path) -> Optional[sqlite3.Connection]:
    """Connexion read-only stricte. None si DB absente/inouvrable (R6)."""
    if not db_path.exists():
        return None
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.OperationalError:
        return None


def _wr_paper_trades(conn: sqlite3.Connection, window: int) -> tuple[Optional[float], int]:
    """WR des `window` derniers paper_trades clôturés. (None, 0) si vide."""
    try:
        rows = conn.execute(
            """
            SELECT is_win FROM paper_trades
            WHERE closed_at IS NOT NULL AND is_win IS NOT NULL
            ORDER BY closed_at DESC LIMIT ?
            """,
            (max(1, window),),
        ).fetchall()
    except sqlite3.OperationalError:
        return None, 0
    if not rows:
        return None, 0
    n = len(rows)
    return sum(int(r[0] or 0) for r in rows) / n, n


def _wr_decisions(conn: sqlite3.Connection, window: int) -> tuple[Optional[float], int]:
    """WR des `window` dernières decisions résolues (DYNAMIC). (None, 0) si vide."""
    try:
        rows = conn.execute(
            """
            SELECT is_win FROM decisions
            WHERE resolved_at IS NOT NULL AND is_win IS NOT NULL
            ORDER BY resolved_at DESC LIMIT ?
            """,
            (max(1, window),),
        ).fetchall()
    except sqlite3.OperationalError:
        return None, 0
    if not rows:
        return None, 0
    n = len(rows)
    return sum(int(r[0] or 0) for r in rows) / n, n


def _classify(drift_pct: Optional[float]) -> str:
    if drift_pct is None:
        return "none"
    if drift_pct > CRITICAL_THRESHOLD:
        return "CRITICAL"
    if drift_pct > WARN_THRESHOLD:
        return "WARN"
    return "none"


def compute_resolution_drift(
    db_path: Path | str | None = None, window: int = DEFAULT_WINDOW,
) -> ResolutionDrift:
    """Calcule la divergence de WR entre paper_trades et decisions.

    Retourne un `ResolutionDrift`. Défensif (R6) : DB absente/vide → WR None,
    drift None, alerte none (jamais de crash, jamais de faux positif à froid).
    """
    if db_path is None:
        db_path = Path("data/v9_forces.db")
    db_p = Path(db_path) if not isinstance(db_path, Path) else db_path

    conn = _connect_ro(db_p)
    if conn is None:
        return ResolutionDrift(None, None, None, 0, 0, "none")
    try:
        wr_pt, n_pt = _wr_paper_trades(conn, window)
        wr_dec, n_dec = _wr_decisions(conn, window)
    finally:
        conn.close()

    if wr_pt is None or wr_dec is None:
        return ResolutionDrift(wr_pt, wr_dec, None, n_pt, n_dec, "none")

    drift_pct = round(abs(wr_dec - wr_pt) * 100.0, 2)
    return ResolutionDrift(
        wr_paper_trades=round(wr_pt, 4),
        wr_decisions=round(wr_dec, 4),
        drift_pct=drift_pct,
        n_paper_trades=n_pt,
        n_decisions=n_dec,
        alert_level=_classify(drift_pct),
    )

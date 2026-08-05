"""V10 Edge Selector — filtre de conviction basé sur la carte des edges (Sprint R).

Exploite la carte des edges produite par le replay batch (v10_replay_batch) :
seules les paires×TF×direction avec un WR ≥ seuil (historique replay) sont
éligibles à une décision BUY/SELL. Les autres sont downgradées → WAIT.

C'est la sélectivité (doctrine R3/R10) : on ne trade QUE les edges validés
par l'apprentissage, pas tout le marché.

R9 honnête : les edges viennent du replay proxy (close[t+H]-close[t]) —
edge RELATIF, pas PnL Fatman. R10 : compute only.
"""
from __future__ import annotations

import glob
import json
import logging
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger(__name__)

# Configuration par défaut
DEFAULT_MIN_WR = 0.50
DEFAULT_MIN_TRADES = 30


class EdgeSelector:
    """Sélecteur d'edges depuis la carte replay (additif R2)."""

    def __init__(self, edge_map: Optional[Dict] = None,
                 min_wr: float = DEFAULT_MIN_WR,
                 min_trades: int = DEFAULT_MIN_TRADES):
        self.min_wr = min_wr
        self.min_trades = min_trades
        self.edge_map = edge_map or {}

    @classmethod
    def from_replay_batch(cls, report_path: Optional[str] = None) -> "EdgeSelector":
        """Charge la carte des edges depuis le dernier rapport replay batch."""
        path = Path(report_path) if report_path else _latest_replay_batch()
        if path is None or not path.exists():
            log.warning("Aucun rapport replay batch trouvé → selector vide (R6)")
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(edge_map=data.get("edge_map", {}))
        except Exception as exc:
            log.warning("Lecture edge map échouée (R6): %s", type(exc).__name__)
            return cls()

    def is_edge(self, pair: str, timeframe: str, direction: str) -> bool:
        """Le (pair, tf, direction) a-t-il un edge validé ?

        direction ∈ {"BUY","SELL"}. Le replay indique la direction dominante
        (ex "BUY"). On exige que la direction demandée MATCHE la direction
        de l'edge, sinon pas d'edge (pas de trade dans le sens faible).
        """
        key = f"{pair.upper()}|{timeframe.upper()}"
        entry = self.edge_map.get(key)
        if not entry:
            return False
        if entry.get("edge") != "YES":
            return False
        if entry.get("n", 0) < self.min_trades:
            return False
        if entry.get("wr", 0.0) < self.min_wr:
            return False
        # La direction demandée doit MATCHER la direction dominante de l'edge
        # (on ne trade pas le sens faible d'une paire).
        dom_dir = entry.get("direction", "")
        if direction.upper() != dom_dir.upper():
            return False
        return True

    def apply(self, pair: str, timeframe: str, direction: str,
              current_level: str) -> tuple:
        """Applique le filtre edge au setup_level.

        Returns
        -------
        (new_level, was_downgraded, reason)
        """
        if current_level in ("NONE",):
            return current_level, False, "none"
        if self.is_edge(pair, timeframe, direction):
            return current_level, False, "edge_ok"
        # Pas d'edge → downgrade A1/A2 → A3 (pas de trade non-validé)
        if current_level in ("A1", "A2"):
            return "A3", True, "no_edge"
        return current_level, False, "none"


def _latest_replay_batch() -> Optional[Path]:
    """Chemin du rapport replay batch le plus récent."""
    files = sorted(glob.glob("reports/v10_replay_batch_*.json"))
    return Path(files[-1]) if files else None


__all__ = [
    "EdgeSelector",
    "DEFAULT_MIN_WR",
    "DEFAULT_MIN_TRADES",
]

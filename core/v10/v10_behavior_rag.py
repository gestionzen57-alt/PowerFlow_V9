"""V10 Behavior RAG — amplification par analogie sur la mémoire propre (Phase 6, Cognitive Continuum).

RAG léger qui cherche des analogies de comportement dans le REGISTRE
d'interprétation (`v10_behaviors`, BASE 3) — PAS dans le bruit V9.

Leçon du brainstorming : le RAG V8 a échoué car mis AVANT la cohérence. Ici,
on l'applique APRÈS : la mémoire est propre (comportement + sens + résultat),
donc l'analogie est utile.

`analogous_behaviors()` : retrouve les comportements passés dont le contexte
(qualification × régime × coalition × antagonisme) est SIMILAIRE, et retourne
leur WR empirique. C'est "setup similaire au passé → quel WR ?" avec du sens.

Similarité = score de correspondance d'attributs (0-1), pas d'embedding lourd.
R2 additif pur (0 import core/v9/). R6 fail-open. R9 traçable. R10 compute only.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]  # C:\projet\V9
DEFAULT_DB = ROOT / "data" / "v10_behaviors.db"

# Poids des attributs pour la similarité de contexte
ATTR_WEIGHTS = {
    "observation_qualification": 0.4,
    "regime_hmm": 0.3,
    "coalition": 0.15,
    "antagonisme": 0.15,
}


def _connect(db_path: Path):
    if not db_path.exists():
        return None
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)


def _similarity(query: Dict, row: Dict) -> float:
    """Score de similarité de contexte (0-1) entre une requête et une ligne."""
    score = 0.0
    total_w = 0.0
    for attr, w in ATTR_WEIGHTS.items():
        total_w += w
        qv = (query.get(attr) or "").strip().upper()
        rv = (row.get(attr) or "").strip().upper()
        if qv and rv and qv == rv:
            score += w
    return score / total_w if total_w else 0.0


def analogous_behaviors(
    *,
    observation_qualification: str,
    regime_hmm: str = "",
    coalition: str = "",
    antagonisme: str = "",
    top_k: int = 10,
    min_similarity: float = 0.3,
    db_path: Path = DEFAULT_DB,
) -> Dict:
    """Retrouve les comportements passés similaires + leur WR empirique.

    Returns dict {analogies: [...], n_analogies, avg_wr, best}.
    R6 : DB absente/vide → {n_analogies: 0}.
    """
    conn = _connect(db_path)
    if conn is None:
        return {"n_analogies": 0, "analogies": [], "avg_wr": 0.0, "best": None}
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT observation_qualification, regime_hmm, coalition, "
            "antagonisme, is_win, pnl_pips FROM v10_behaviors "
            "WHERE is_win IS NOT NULL"
        ).fetchall()
        cols = ["observation_qualification", "regime_hmm", "coalition",
                "antagonisme", "is_win", "pnl_pips"]
        query = {
            "observation_qualification": observation_qualification,
            "regime_hmm": regime_hmm, "coalition": coalition,
            "antagonisme": antagonisme,
        }
        scored = []
        for r in rows:
            row = dict(zip(cols, r))
            sim = _similarity(query, row)
            if sim >= min_similarity:
                scored.append({
                    "similarity": round(sim, 3),
                    "is_win": row["is_win"],
                    "pnl_pips": row["pnl_pips"],
                    "context": {
                        "qualification": row["observation_qualification"],
                        "regime": row["regime_hmm"],
                        "coalition": row["coalition"],
                        "antagonisme": row["antagonisme"],
                    },
                })
        scored.sort(key=lambda x: -x["similarity"])
        scored = scored[:top_k]
        n = len(scored)
        n_wins = sum(1 for s in scored if s["is_win"])
        avg_wr = round(n_wins / n, 3) if n else 0.0
        best = scored[0] if scored else None
        return {
            "n_analogies": n,
            "analogies": scored,
            "avg_wr": avg_wr,
            "best": best,
            "audit": {"r10": "compute only"},
        }
    except Exception as exc:
        log.warning("analogous_behaviors échoué (R6): %s", exc)
        return {"n_analogies": 0, "analogies": [], "avg_wr": 0.0, "best": None}
    finally:
        conn.close()


__all__ = ["analogous_behaviors", "ATTR_WEIGHTS"]

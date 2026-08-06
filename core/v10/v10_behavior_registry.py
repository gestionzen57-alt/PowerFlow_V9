"""V10 Behavior Registry — Registre d'interprétation (Phase 2, Cognitive Continuum).

BASE 3 (Apprentissage/cohérence) de l'architecture Cognitive Continuum :
transforme l'observation en COMPRÉHENSION. Chaque ligne = une observation
V9 (matière première) INTERPRÉTÉE à la lumière du contexte V10 (régime,
Fatman, structure, coalition) + le RÉSULTAT (win/loss).

C'est ici que naît le sens : "quand coalition X + régime Y + antagonisme Z
→ quel WR réel ?" — la requête de cohérence qui rend le WR signifiant.

Table `v10_behaviors` (DB séparée `data/v10_behaviors.db`, R8) :
  id, timestamp, pair, timeframe
  observation_qualification (V9 : maintien/bascule/tension/...)
  regime_hmm, coalition, antagonisme, structure_type, safe_haven
  resultat : is_win, pnl_pips
  audit : source (v9 behaviors ref), r10

R2 additif pur (0 import core/v9/). R6 fail-open. R9 traçable. R10 compute only.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]  # C:\projet\V9
DEFAULT_DB = ROOT / "data" / "v10_behaviors.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS v10_behaviors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    pair TEXT,
    timeframe TEXT,
    observation_qualification TEXT,
    regime_hmm TEXT,
    coalition TEXT,
    antagonisme TEXT,
    structure_type TEXT,
    safe_haven TEXT,
    is_win INTEGER,
    pnl_pips REAL,
    source_ref TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_v10_behaviors_ctx
    ON v10_behaviors(observation_qualification, regime_hmm, coalition, antagonisme);
"""


def _connect(db_path: Path, write: bool = False) -> sqlite3.Connection:
    if write:
        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        return conn
    if not db_path.exists():
        return None
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)


def record_behavior(
    *,
    timestamp: str,
    pair: str,
    timeframe: str,
    observation_qualification: str,
    regime_hmm: str = "",
    coalition: str = "",
    antagonisme: str = "",
    structure_type: str = "",
    safe_haven: str = "",
    is_win: Optional[int] = None,
    pnl_pips: Optional[float] = None,
    source_ref: str = "",
    db_path: Path = DEFAULT_DB,
) -> int:
    """Enregistre une interprétation (observation + contexte + résultat).

    Returns l'id inséré. R6 : DB non ouvrable → -1 (jamais de crash).
    """
    conn = _connect(db_path, write=True)
    if conn is None:
        return -1
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO v10_behaviors
               (timestamp, pair, timeframe, observation_qualification,
                regime_hmm, coalition, antagonisme, structure_type, safe_haven,
                is_win, pnl_pips, source_ref, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))""",
            (timestamp, pair, timeframe, observation_qualification,
             regime_hmm, coalition, antagonisme, structure_type, safe_haven,
             is_win, pnl_pips, source_ref),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as exc:
        log.warning("record_behavior échoué (R6): %s", exc)
        return -1
    finally:
        conn.close()


def query_coherence(
    *,
    observation_qualification: str = "",
    regime_hmm: str = "",
    coalition: str = "",
    antagonisme: str = "",
    min_n: int = 5,
    db_path: Path = DEFAULT_DB,
) -> Dict:
    """Requête de cohérence : WR réel d'un contexte de comportement.

    "quand coalition X + régime Y + antagonisme Z → quel WR ?"
    R6 : DB absente/vide → {n:0, wr:0}. R9 : chaque chiffre sourcé.
    """
    conn = _connect(db_path)
    if conn is None:
        return {"n": 0, "wr": 0.0, "n_wins": 0, "reason": "no_db"}
    try:
        cur = conn.cursor()
        q = "SELECT COUNT(*), COALESCE(SUM(is_win),0) FROM v10_behaviors WHERE 1=1"
        params: List = []
        if observation_qualification:
            q += " AND observation_qualification=?"
            params.append(observation_qualification)
        if regime_hmm:
            q += " AND regime_hmm=?"
            params.append(regime_hmm)
        if coalition:
            q += " AND coalition=?"
            params.append(coalition)
        if antagonisme:
            q += " AND antagonisme=?"
            params.append(antagonisme)
        n, n_wins = cur.execute(q, params).fetchone()
        n = n or 0
        n_wins = n_wins or 0
        if n < min_n:
            return {"n": n, "wr": 0.0, "n_wins": n_wins,
                    "reason": f"insufficient_n_{n}<{min_n}"}
        return {"n": n, "wr": round(n_wins / n, 3), "n_wins": n_wins,
                "reason": "ok"}
    except Exception as exc:
        log.warning("query_coherence échoué (R6): %s", exc)
        return {"n": 0, "wr": 0.0, "n_wins": 0, "reason": "error"}
    finally:
        conn.close()


def registry_summary(db_path: Path = DEFAULT_DB) -> Dict:
    """État global du registre (R9 audit)."""
    conn = _connect(db_path)
    if conn is None:
        return {"status": "no_db", "n_behaviors": 0}
    try:
        cur = conn.cursor()
        n = cur.execute("SELECT COUNT(*) FROM v10_behaviors").fetchone()[0]
        n_resolved = cur.execute(
            "SELECT COUNT(*) FROM v10_behaviors WHERE is_win IS NOT NULL"
        ).fetchone()[0]
        by_qual = dict(cur.execute(
            "SELECT observation_qualification, COUNT(*) FROM v10_behaviors "
            "GROUP BY observation_qualification ORDER BY 2 DESC"
        ).fetchall())
        return {
            "status": "ok",
            "n_behaviors": n,
            "n_resolved": n_resolved,
            "by_qualification": by_qual,
            "source": str(db_path),
        }
    except Exception as exc:
        log.warning("registry_summary échoué (R6): %s", exc)
        return {"status": "error", "n_behaviors": 0}
    finally:
        conn.close()


__all__ = [
    "record_behavior",
    "query_coherence",
    "registry_summary",
    "DEFAULT_DB",
]

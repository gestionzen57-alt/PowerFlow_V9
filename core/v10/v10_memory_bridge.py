"""V10 Memory Bridge — pont mémoire V9→V10 (Phase 1, Cognitive Continuum).

Lit la mémoire inter-cycles V9 (`data/v9_cycle_memory.db`, 201 patterns) en
LECTURE SEULE (R2 additif pur : 0 import core/v9/, on lit la DB directement)
et l'expose à V10 comme contexte de décision.

BASE 5 (Mémoire) de l'architecture Cognitive Continuum :
  - `recall_patterns(symbol, timeframe, regime_type, phase)` → patterns
    inter-cycles résolus (WR empirique, confidence).
  - `get_transition_distribution(...)` → P(phase_T | phase_T-1, ...).
  - `memory_summary()` → état global de la mémoire (n patterns, par régime).

R6 fail-open : DB absente/vide → dict vide, jamais de crash.
R9 : chaque lecture tracée (source = v9_cycle_memory.db, read-only).
R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]  # C:\projet\V9
DEFAULT_DB = ROOT / "data" / "v9_cycle_memory.db"


def _connect(db_path: Path) -> Optional[sqlite3.Connection]:
    """Connexion read-only (R2 : ne jamais écrire dans la mémoire V9)."""
    if not db_path.exists():
        return None
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    except Exception as exc:
        log.warning("Connexion mémoire V9 échouée (R6): %s", exc)
        return None


def recall_patterns(
    symbol: str,
    timeframe: str,
    regime_type: str = "",
    phase: str = "",
    db_path: Path = DEFAULT_DB,
) -> List[Dict]:
    """Rappelle les patterns inter-cycles résolus pour un contexte.

    Lit `cycle_patterns` (mémoire V9) en lecture seule. Retourne les patterns
    dont le contexte (symbol/timeframe/regime_type/phase) correspond, avec
    WR empirique + confidence.

    R6 : DB absente/vide → [] (jamais de crash).
    """
    conn = _connect(db_path)
    if conn is None:
        return []
    try:
        cur = conn.cursor()
        # Vérifier que la table existe
        row = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cycle_patterns'"
        ).fetchone()
        if row is None:
            return []
        q = ("SELECT symbol, timeframe, regime_type, phase, vol_atr_bucket, "
             "n_observations, n_resolved, n_wins, last_updated_ts "
             "FROM cycle_patterns "
             "WHERE symbol=? AND timeframe=?")
        params: List = [symbol, timeframe]
        if regime_type:
            q += " AND regime_type=?"
            params.append(regime_type)
        if phase:
            q += " AND phase=?"
            params.append(phase)
        q += " ORDER BY n_observations DESC LIMIT 20"
        rows = cur.execute(q, params).fetchall()
        cols = ["symbol", "timeframe", "regime_type", "phase", "vol_atr_bucket",
                "n_observations", "n_resolved", "n_wins", "last_updated_ts"]
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            n_res = d.get("n_resolved") or 0
            n_win = d.get("n_wins") or 0
            d["wr"] = round(n_win / n_res, 3) if n_res else 0.0
            d["confidence"] = round(n_res / 30.0, 2) if n_res else 0.0
            out.append(d)
        return out
    except Exception as exc:
        log.warning("Recall mémoire V9 échoué (R6): %s", exc)
        return []
    finally:
        conn.close()


def get_transition_distribution(
    from_phase: str,
    symbol: str = "",
    timeframe: str = "",
    regime_type: str = "",
    db_path: Path = DEFAULT_DB,
) -> Dict:
    """Distribution empirique P(phase_T | phase_T-1, ...) depuis la mémoire V9.

    Lit `transition_patterns` si présente, sinon retourne {} (R6).
    """
    conn = _connect(db_path)
    if conn is None:
        return {}
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transition_patterns'"
        ).fetchone()
        if row is None:
            return {}
        q = ("SELECT to_phase, COUNT(*) as n FROM transition_patterns "
             "WHERE from_phase=?")
        params: List = [from_phase]
        if symbol:
            q += " AND symbol=?"
            params.append(symbol)
        if timeframe:
            q += " AND timeframe=?"
            params.append(timeframe)
        if regime_type:
            q += " AND regime_type=?"
            params.append(regime_type)
        q += " GROUP BY to_phase ORDER BY n DESC"
        rows = cur.execute(q, params).fetchall()
        total = sum(r[1] for r in rows) or 1
        return {r[0]: round(r[1] / total, 3) for r in rows}
    except Exception as exc:
        log.warning("Transition mémoire V9 échouée (R6): %s", exc)
        return {}
    finally:
        conn.close()


def memory_summary(db_path: Path = DEFAULT_DB) -> Dict:
    """État global de la mémoire inter-cycles V9 (R9 audit)."""
    conn = _connect(db_path)
    if conn is None:
        return {"status": "no_db", "n_patterns": 0}
    try:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cycle_patterns'"
        ).fetchone()
        if row is None:
            return {"status": "no_table", "n_patterns": 0}
        n = cur.execute("SELECT COUNT(*) FROM cycle_patterns").fetchone()[0]
        by_regime = dict(cur.execute(
            "SELECT regime_type, COUNT(*) FROM cycle_patterns GROUP BY regime_type"
        ).fetchall())
        return {
            "status": "ok",
            "n_patterns": n,
            "by_regime": by_regime,
            "source": str(db_path),
            "read_only": True,
        }
    except Exception as exc:
        log.warning("Summary mémoire V9 échoué (R6): %s", exc)
        return {"status": "error", "n_patterns": 0}
    finally:
        conn.close()


__all__ = [
    "recall_patterns",
    "get_transition_distribution",
    "memory_summary",
    "DEFAULT_DB",
]

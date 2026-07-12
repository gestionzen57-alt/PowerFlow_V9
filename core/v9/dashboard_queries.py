"""dashboard_queries.py — requêtes lecture seule pour le dashboard web HITL (Brief Q3).

Doctrine : STRICTEMENT lecture seule sur `data/v9_forces.db` (WAL, mêmes
pragmas que le reste de V9 via `core.v9.db_schema.get_connection`). Aucune
fonction de ce module n'écrit en base — les seules écritures du Brief Q3
(validations opérateur `/review`) passent par `core.v9.hitl_reviews_db`,
jamais par ici.

Réutilise le pipeline existant plutôt que de le réimplémenter :
  - `core.v9.memory_query.get_current_state()` pour l'état courant.
  - `core.v9.auto_calibrator._session_wr_buckets()` (Brief Q2) pour les
    stats par session — appelé directement (pas via `run_calibration_cycle`,
    qui court-circuite si le kill switch calibrateur est OFF ; la vue
    dashboard doit rester utilisable indépendamment de ce switch).
  - `core.v9.principle_scorer.PrincipleScorer.get_top_combinations()` et
    `scripts.v9_scoring._compute_scoring()` pour le scoring par principe.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.v9.auto_calibrator import _session_wr_buckets
from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection
from core.v9.hitl_reviews_db import get_reviews_for_decision
from core.v9.memory_query import get_current_state
from core.v9.principle_scorer import PrincipleScorer

HITL_CONF_LOW = 40
HITL_CONF_HIGH = 65


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# ── / — accueil ──────────────────────────────────────────────────────
def get_home_snapshot(db_path: Path | None = None) -> dict[str, Any]:
    """Dernier snapshot/décision + P&L paper agrégé."""
    state = get_current_state(db_path=db_path)

    conn = get_connection(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        pnl = {"n_trades": 0, "n_wins": 0, "n_losses": 0, "total_pips": 0.0, "avg_pips": 0.0}
        if _table_exists(conn, "paper_trades"):
            row = conn.execute(
                "SELECT COUNT(*) AS n, "
                "SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) AS wins, "
                "SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) AS losses, "
                "SUM(pips_simulated) AS total_pips "
                "FROM paper_trades WHERE closed_at IS NOT NULL"
            ).fetchone()
            n = row["n"] or 0
            total_pips = row["total_pips"] or 0.0
            pnl = {
                "n_trades": n,
                "n_wins": row["wins"] or 0,
                "n_losses": row["losses"] or 0,
                "total_pips": round(total_pips, 1),
                "avg_pips": round(total_pips / n, 2) if n else 0.0,
            }
        return {"state": state, "paper_pnl": pnl}
    finally:
        conn.close()


# ── /review — file HITL ──────────────────────────────────────────────
def get_hitl_queue(db_path: Path | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Décisions directionnelles confiance 40-65 (informatif) ou
    low_confidence_block=1 (<40) — la file HITL Brief O3, enrichie de
    l'historique de validation opérateur (`hitl_reviews`, si existant)."""
    conn = get_connection(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "decisions"):
            return []
        rows = conn.execute(
            "SELECT decision_id, timestamp, symbol, timeframe, direction, confiance, "
            "principes_json, low_confidence_block "
            "FROM decisions "
            "WHERE direction IS NOT NULL AND direction != 'neutre' "
            "AND (confiance BETWEEN ? AND ? OR low_confidence_block = 1) "
            "ORDER BY timestamp DESC LIMIT ?",
            (HITL_CONF_LOW, HITL_CONF_HIGH, limit),
        ).fetchall()

        queue = []
        for r in rows:
            d = dict(r)
            d["tier"] = (
                "blocked_low_confidence"
                if d.get("low_confidence_block") == 1
                else "informative_40_65"
            )
            d["reviews"] = get_reviews_for_decision(d["decision_id"], db_path=db_path or DB_PATH)
            queue.append(d)
        return queue
    finally:
        conn.close()


# ── /trades — historique paper trades ────────────────────────────────
def get_paper_trades(db_path: Path | None = None, limit: int = 200) -> list[dict[str, Any]]:
    conn = get_connection(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "paper_trades"):
            return []
        rows = conn.execute(
            "SELECT trade_id, snapshot_id, direction, confiance, opened_at, closed_at, "
            "pips_simulated, is_win "
            "FROM paper_trades ORDER BY opened_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── /calibration — principle_scores + stats par session ──────────────
def get_calibration_view(db_path: Path | None = None) -> dict[str, Any]:
    """Scoring par principe (réutilise PrincipleScorer + v9_scoring) +
    répartition WR par session (réutilise `_session_wr_buckets` du
    Brief Q2, indépendamment du kill switch auto-calibrateur)."""
    resolved_db_path = Path(db_path) if db_path else DB_PATH

    conn = get_connection(resolved_db_path)
    conn.row_factory = sqlite3.Row
    try:
        buckets = _session_wr_buckets(conn) if _table_exists(conn, "decisions") else {}
    finally:
        conn.close()

    scorer = PrincipleScorer(db_path=resolved_db_path)
    top_combinations = scorer.get_top_combinations(limit=15, min_trades=5)

    per_principle = []
    try:
        from scripts.v9_scoring import _compute_scoring  # noqa: PLC0415

        conn2 = get_connection(resolved_db_path)
        conn2.row_factory = sqlite3.Row
        try:
            per_principle = _compute_scoring(conn2, min_samples=0)
        finally:
            conn2.close()
    except Exception:
        per_principle = []

    return {
        "session_buckets": buckets,
        "top_combinations": top_combinations,
        "per_principle": per_principle,
    }

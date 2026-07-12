"""hitl_reviews_db.py — table `hitl_reviews` (data/v9_forces.db).

Brief Q3 (2026-07-12) : dashboard web HITL. Les validations opérateur sur
la file HITL (Brief O3 : confiance 40-65 informatif, low_confidence_block
confiance<40) sont journalisées ICI, jamais dans `decisions` — `decisions`
reste la trace brute du pipeline cognitif, `hitl_reviews` est un journal
d'audit humain séparé, sans écriture rétroactive sur une décision déjà
loggée (aucune fonction de ce module n'exécute UPDATE/INSERT sur
`decisions`).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.v9.db_schema import get_connection

HITL_REVIEWS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hitl_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('approved', 'rejected')),
    reviewer TEXT,
    comment TEXT,
    reviewed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hitl_reviews_decision_id
    ON hitl_reviews (decision_id);
"""

VALID_VERDICTS = ("approved", "rejected")


def init_hitl_reviews_db(db_path: Path | None = None) -> None:
    """Crée la table hitl_reviews et son index si absents (idempotent)."""
    conn = get_connection(db_path)
    try:
        conn.executescript(HITL_REVIEWS_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def insert_review(
    decision_id: str,
    verdict: str,
    reviewer: str | None = None,
    comment: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Journalise une validation opérateur. Écrit UNIQUEMENT dans hitl_reviews."""
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"verdict invalide: {verdict!r} (attendu {VALID_VERDICTS})")
    if not decision_id:
        raise ValueError("decision_id requis")

    init_hitl_reviews_db(db_path)
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO hitl_reviews (decision_id, verdict, reviewer, comment, reviewed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (decision_id, verdict, reviewer, comment, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_reviews_for_decision(decision_id: str, db_path: Path | None = None) -> list[dict]:
    """Historique des validations pour une décision (le plus récent d'abord)."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "hitl_reviews"):
            return []
        rows = conn.execute(
            "SELECT * FROM hitl_reviews WHERE decision_id = ? ORDER BY id DESC",
            (decision_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_reviews(limit: int = 100, db_path: Path | None = None) -> list[dict]:
    """Dernières validations toutes décisions confondues (pour affichage dashboard)."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "hitl_reviews"):
            return []
        rows = conn.execute(
            "SELECT * FROM hitl_reviews ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None

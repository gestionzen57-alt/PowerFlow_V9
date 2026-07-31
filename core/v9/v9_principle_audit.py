"""v9_principle_audit.py — Phase 14 motion CEO « EDGE FUND MAX ».

BUG-P3 follow-up (Phase 13 fix structurel UPSERT a preserve v9_status,
mais aucun audit trail pour tracer QUI a change QUOI/QUAND). Si Søn
doit auditer, il faut un journal de bord.

Module : ecrit dans la table principle_audit_log (nouvelle) a chaque
changement de v9_status, created_at_source, source_status. Lecture de
l'historique par principle_id pour audit motion CEO.

Note : schema migrate-once, idempotent.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("v9.principle_audit")


def _ensure_audit_table(db_path: Path | str) -> None:
    """Cree la table principle_audit_log si absente (idempotent)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS principle_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                principle_id TEXT NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                actor TEXT,
                reason TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_principle
            ON principle_audit_log (principle_id, ts DESC)
        """)
        conn.commit()
    finally:
        conn.close()


def log_change(
    db_path: Path | str,
    principle_id: str,
    field: str,
    old_value: str | None,
    new_value: str | None,
    *,
    actor: str = "system",
    reason: str = "",
) -> None:
    """Enregistre un changement de colonne sur un principe.

    field ∈ {v9_status, source_status, created_at_source, ...}
    """
    if old_value == new_value:
        return
    _ensure_audit_table(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            INSERT INTO principle_audit_log
            (ts, principle_id, field, old_value, new_value, actor, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            principle_id, field,
            str(old_value) if old_value is not None else None,
            str(new_value) if new_value is not None else None,
            actor, reason,
        ))
        conn.commit()
    finally:
        conn.close()


def get_audit_history(
    db_path: Path | str,
    principle_id: str,
    *,
    field: str | None = None,
    limit: int = 50,
) -> list[dict[str, str | None]]:
    """Retourne l'historique d'un principe (recent first)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    _ensure_audit_table(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if field:
            rows = conn.execute("""
                SELECT * FROM principle_audit_log
                WHERE principle_id = ? AND field = ?
                ORDER BY ts DESC LIMIT ?
            """, (principle_id, field, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM principle_audit_log
                WHERE principle_id = ?
                ORDER BY ts DESC LIMIT ?
            """, (principle_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def sync_with_audit(
    db_path: Path | str,
    *,
    actor: str = "principle_engine",
    reason: str = "sync_catalogue",
) -> int:
    """Compare DB principles avec UPSERT et log les changements detectes.

    Si un principle a deja v9_status en DB et l'engine propose un autre,
    on log le changement via log_change(). Retourne nb changements detectes.

    Usage : appele apres _sync_principles_to_db() pour tracer ce qui
    aurait pu etre perdu par l'ancien INSERT OR REPLACE.
    """
    from core.v9.principle_engine import PrincipleEngine
    _ensure_audit_table(db_path)
    engine = PrincipleEngine(db_path=str(db_path))
    engine.load()

    # Lire etat actuel en DB
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    current = {}
    try:
        for r in conn.execute(
            "SELECT principle_id, v9_status, source_status, created_at_source "
            "FROM principles"
        ).fetchall():
            current[str(r["principle_id"])] = dict(r)
    finally:
        conn.close()

    n_changes = 0
    for p in engine.principles:
        pid = p.principle_id
        if pid not in current:
            # Nouveau principe
            log_change(db_path, pid, "v9_status", None, p.v9_status,
                       actor=actor, reason=f"{reason} (new)")
            n_changes += 1
            continue
        cur = current[pid]
        if cur["v9_status"] != p.v9_status:
            log_change(db_path, pid, "v9_status",
                       cur["v9_status"], p.v9_status,
                       actor=actor, reason=reason)
            n_changes += 1
        if cur["source_status"] != p.source_status:
            log_change(db_path, pid, "source_status",
                       cur["source_status"], p.source_status,
                       actor=actor, reason=reason)
            n_changes += 1
    return n_changes
"""cognitive_journal.py — JOURNAL COGNITIF : boucle de correction V9 ↔ Søn.

V9 lit le marché avec des règles binaires (YAML). Søn lit le marché avec
10 ans d'expérience. Ce module capture ce que V9 voit (`log_v9_reading`,
via `memory_query.get_market_narrative`), permet d'enregistrer ce que
Søn corrige (`log_son_correction`), trace les différences (`corrections`)
et fait émerger des règles apprises quand un même écart se répète
(`learn_from_corrections`).

Base dédiée `data/v9_cognitive.db` (jamais `data/v9_forces.db`) — lecture
seule sur la chaîne cognitive V9 via `memory_query`, écriture uniquement
sur ce nouveau journal. 0 modification de core/v9/config.py,
orchestrator.py, principle_engine.py, principles/*.yaml. 0 dépendance
pip (stdlib + sqlite3 + json).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.memory_query import get_current_state, get_market_narrative

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "data" / "v9_cognitive.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    v9_narrative TEXT,
    son_correction TEXT,
    direction_v9 TEXT,
    direction_son TEXT,
    patterns_v9 TEXT,
    patterns_son TEXT,
    learned INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_id INTEGER NOT NULL,
    field TEXT NOT NULL,
    v9_value TEXT,
    son_value TEXT,
    applied INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correction_id INTEGER,
    rule TEXT NOT NULL UNIQUE,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_readings_pending
    ON readings (source, son_correction);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Connexion sqlite3 vers le journal cognitif, schéma auto-créé (idempotent)."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA_SQL)
    return conn


def init_cognitive_db(db_path: Path | None = None) -> None:
    """Crée les 3 tables du journal cognitif si absentes. Idempotent."""
    _connect(db_path).close()


def _dominant_direction(signals: list[dict[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for s in signals:
        direction = s.get("direction")
        if direction:
            counts[direction] = counts.get(direction, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _parse_patterns(value: Any) -> list[str]:
    """Normalise une liste de patterns depuis JSON, liste, CSV ou None."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return [p.strip() for p in value.split(",") if p.strip()]
    return []


# ── 1. Capture — ce que V9 voit ──────────────────────────────────────
def log_v9_reading(market_db_path: Path | None = None, db_path: Path | None = None) -> int:
    """Capture l'état courant V9 (narrative + direction + patterns) dans le journal.

    `market_db_path` : DB source lue en lecture seule (`data/v9_forces.db`
    par défaut, via `memory_query`). `db_path` : DB du journal cognitif
    (`data/v9_cognitive.db` par défaut). Retourne le reading_id créé.
    """
    narrative = get_market_narrative(db_path=market_db_path)
    state = get_current_state(db_path=market_db_path)
    direction_v9 = _dominant_direction(state.get("signals") or [])
    patterns_v9 = sorted(
        {p.get("principle_id") for p in (state.get("principle_evaluations") or []) if p.get("principle_id")}
    )

    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO readings (timestamp, source, v9_narrative, direction_v9, patterns_v9, learned) "
            "VALUES (?, 'v9', ?, ?, ?, 0)",
            (
                datetime.now(timezone.utc).isoformat(),
                narrative,
                direction_v9,
                json.dumps(patterns_v9),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_reading(reading_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    """Retourne une lecture par id, ou None si absente."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM readings WHERE id = ?", (reading_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── 2. Correction — ce que Søn voit ──────────────────────────────────
def log_son_correction(
    reading_id: int,
    narrative: str,
    direction: str | None,
    patterns_json: Any = None,
    db_path: Path | None = None,
) -> None:
    """Enregistre la correction de Søn sur une lecture V9 et trace les écarts.

    Met à jour `readings` (son_correction/direction_son/patterns_son) puis
    compare aux champs V9 : tout écart de direction ou pattern absent côté
    V9 devient une ligne dans `corrections` (matière première de
    `learn_from_corrections`). Silencieux si `reading_id` est inconnu.
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT direction_v9, patterns_v9 FROM readings WHERE id = ?", (reading_id,)
        ).fetchone()
        if row is None:
            return
        direction_v9 = row["direction_v9"]
        patterns_v9 = _parse_patterns(row["patterns_v9"])
        patterns_son = _parse_patterns(patterns_json)

        conn.execute(
            "UPDATE readings SET son_correction = ?, direction_son = ?, patterns_son = ? WHERE id = ?",
            (narrative, direction, json.dumps(patterns_son), reading_id),
        )

        differences: list[tuple[str, str, str]] = []
        if direction and direction_v9 and direction != direction_v9:
            differences.append(("direction", direction_v9, direction))

        v9_context = ",".join(patterns_v9) if patterns_v9 else (direction_v9 or "neutre")
        for pattern in patterns_son:
            if pattern not in patterns_v9:
                differences.append(("missing_pattern", v9_context, pattern))

        for field, v9_value, son_value in differences:
            conn.execute(
                "INSERT INTO corrections (reading_id, field, v9_value, son_value, applied) "
                "VALUES (?, ?, ?, ?, 0)",
                (reading_id, field, v9_value, son_value),
            )
        conn.commit()
    finally:
        conn.close()


# ── 3. Lectures en attente de correction ─────────────────────────────
def get_pending_corrections(limit: int = 5, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Les `limit` lectures V9 les plus anciennes sans correction Søn."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM readings WHERE source = 'v9' AND son_correction IS NULL "
            "ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── 4. Leçons apprises ────────────────────────────────────────────────
def get_lessons(confidence_min: float = 0.3, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Leçons de confiance >= `confidence_min`, les plus sûres d'abord."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM lessons WHERE confidence >= ? ORDER BY confidence DESC, id DESC",
            (confidence_min,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _build_rule(field: str, v9_value: str, son_value: str) -> str:
    if field == "direction":
        return f"Quand V9 voit direction={v9_value or 'indéterminée'}, Søn corrige vers {son_value}."
    if field == "missing_pattern":
        return f"Quand V9 voit {v9_value or 'contexte neutre'}, vérifier {son_value}."
    return f"Quand V9 voit {field}={v9_value}, Søn corrige vers {son_value}."


# ── 5. Apprentissage — pattern de correction répété ≥3 fois ─────────
def learn_from_corrections(min_occurrences: int = 3, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Regroupe les corrections non appliquées par (field, v9_value, son_value).

    Tout groupe atteignant `min_occurrences` devient (ou met à jour) une
    leçon — confiance croissante avec le nombre d'occurrences, plafonnée
    à 1.0. Les corrections consommées sont marquées `applied=1`. Retourne
    les leçons nouvellement créées (dict avec id/rule/confidence).
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, field, v9_value, son_value FROM corrections WHERE applied = 0"
        ).fetchall()

        groups: dict[tuple[str, str, str], list[int]] = {}
        for r in rows:
            key = (r["field"], r["v9_value"] or "", r["son_value"] or "")
            groups.setdefault(key, []).append(r["id"])

        created: list[dict[str, Any]] = []
        for (field, v9_value, son_value), ids in groups.items():
            count = len(ids)
            if count < min_occurrences:
                continue
            rule = _build_rule(field, v9_value, son_value)
            confidence = min(1.0, 0.3 + 0.1 * (count - min_occurrences))
            existing = conn.execute("SELECT id FROM lessons WHERE rule = ?", (rule,)).fetchone()
            if existing is None:
                cur = conn.execute(
                    "INSERT INTO lessons (correction_id, rule, confidence, created_at) VALUES (?, ?, ?, ?)",
                    (ids[-1], rule, confidence, datetime.now(timezone.utc).isoformat()),
                )
                created.append({"id": cur.lastrowid, "rule": rule, "confidence": confidence})
            else:
                conn.execute("UPDATE lessons SET confidence = ? WHERE id = ?", (confidence, existing["id"]))
            conn.executemany(
                "UPDATE corrections SET applied = 1 WHERE id = ?", [(i,) for i in ids]
            )
            conn.executemany(
                "UPDATE readings SET learned = 1 WHERE id = "
                "(SELECT reading_id FROM corrections WHERE id = ?)",
                [(i,) for i in ids],
            )
        conn.commit()
        return created
    finally:
        conn.close()

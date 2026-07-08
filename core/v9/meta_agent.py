"""meta_agent.py — META-AGENT V9 (Phase 15, apprentissage autonome).

Chaîne : Bus (agent_event_bus) → [META-AGENT] → proposals (bus, event_type
='proposal') + cognitive_journal.lessons.

Le meta-agent est un CONSOMMATEUR passif du bus : il lit les events non
consommés, détecte des patterns récurrents, et PROPOSE des actions — il
n'agit jamais lui-même (toute proposition reste soumise à validation Søn,
doctrine R25'). Premier agent à surveiller le bus (agents/AGENTIC_MAP.md
notait le bus comme opérationnel mais sans consommateur).

NOTE — bootstrap infra : ni `agent_event_bus` ni `cognitive_journal`
n'existaient dans le schéma V9 avant ce module (11 tables recensées dans
`core/v9/db_schema.py`). Les deux tables sont créées ici, idempotentes
(CREATE TABLE IF NOT EXISTS), sur la même DB (data/v9_forces.db), suivant
le schéma déjà documenté dans `skills/powerflow-bridge-bus/SKILL.md`.

Doctrine respectée :
- R8 : 0 modification core/v9/config.py, orchestrator.py,
  principle_engine.py, principles/*.yaml (lecture seule sur ces sources).
- R18 : zéro LLM, zéro appel réseau — patterns détectés par comptage SQL pur.
- R25' : le meta-agent PROPOSE, il ne PROMEUT ni ne modifie jamais un YAML.
- 0 dépendance pip (stdlib only : sqlite3, json, time, collections).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any

from core.v9.config import PRINCIPLES_DIR
from core.v9.db_schema import get_connection

# ── Schéma bus + journal (bootstrap, absents avant ce module) ──────────
SCHEMA_BUS = """
CREATE TABLE IF NOT EXISTS agent_event_bus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    producer TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    consumed_by TEXT,
    correlation_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_bus_ts ON agent_event_bus (ts);
CREATE INDEX IF NOT EXISTS idx_bus_event_type ON agent_event_bus (event_type, consumed_by);
"""

SCHEMA_JOURNAL = """
CREATE TABLE IF NOT EXISTS cognitive_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    lessons TEXT NOT NULL,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_journal_event_type ON cognitive_journal (event_type, ts);
"""

# ── Seuils de détection (spec CEO) ──────────────────────────────────────
FREQUENT_THRESHOLD = 50       # a. même event_type > 50x / fenêtre
COMBO_THRESHOLD = 10          # b. même (event_type + payload signature) > 10x
CORRECTION_THRESHOLD = 3      # c. même correction Søn > 3x
PROPOSAL_CONFIDENCE_MIN = 0.5


def _conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Connexion sqlite3 V9 + garantit bus/journal présents (idempotent)."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_BUS)
    conn.executescript(SCHEMA_JOURNAL)
    conn.commit()
    return conn


def _payload_signature(payload_raw: str) -> str:
    """Signature stable d'un payload JSON pour regrouper les combinaisons similaires."""
    try:
        payload = json.loads(payload_raw)
    except (json.JSONDecodeError, TypeError):
        return str(payload_raw)[:80]
    if isinstance(payload, dict):
        return "|".join(sorted(payload.keys()))
    return str(payload)[:80]


def scan_patterns(hours: int = 24, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Scanne les events non consommés du bus (fenêtre `hours`) + cognitive_journal.

    Détecte 3 familles de patterns :
    a. pattern_frequent    — même event_type > FREQUENT_THRESHOLD occurrences.
    b. pattern_combinaison — même (event_type + signature payload) > COMBO_THRESHOLD.
    c. pattern_correction  — même correction Søn > CORRECTION_THRESHOLD (cognitive_journal).
    """
    conn = _conn(db_path)
    try:
        since_ms = int((time.time() - hours * 3600) * 1000)
        rows = conn.execute(
            "SELECT event_type, payload FROM agent_event_bus "
            "WHERE ts >= ? AND consumed_by IS NULL",
            (since_ms,),
        ).fetchall()

        patterns: list[dict[str, Any]] = []

        type_counts = Counter(r["event_type"] for r in rows)
        for event_type, count in type_counts.items():
            if count > FREQUENT_THRESHOLD:
                patterns.append({
                    "pattern_type": "pattern_frequent",
                    "event_type": event_type,
                    "frequency": count,
                    "window_hours": hours,
                })

        combo_counts = Counter(
            (r["event_type"], _payload_signature(r["payload"])) for r in rows
        )
        for (event_type, signature), count in combo_counts.items():
            if count > COMBO_THRESHOLD:
                patterns.append({
                    "pattern_type": "pattern_combinaison",
                    "event_type": event_type,
                    "signature": signature,
                    "frequency": count,
                    "window_hours": hours,
                })

        correction_rows = conn.execute(
            "SELECT lessons FROM cognitive_journal "
            "WHERE event_type = 'correction' AND ts >= ?",
            (since_ms,),
        ).fetchall()
        correction_counts = Counter(r["lessons"] for r in correction_rows)
        for lesson, count in correction_counts.items():
            if count > CORRECTION_THRESHOLD:
                patterns.append({
                    "pattern_type": "pattern_correction",
                    "lesson": lesson,
                    "frequency": count,
                    "window_hours": hours,
                })

        return patterns
    finally:
        conn.close()


def propose_action(pattern: dict[str, Any]) -> dict[str, Any]:
    """Traduit un pattern détecté en proposition d'action concrète.

    Retourne toujours action_type/target/rationale/confidence — jamais
    n'exécute l'action (R25' : la décision reste à Søn).
    """
    pattern_type = pattern.get("pattern_type")
    frequency = pattern.get("frequency", 0)
    window_hours = pattern.get("window_hours", 24)

    if pattern_type == "pattern_frequent":
        event_type = pattern.get("event_type", "")
        yaml_exists = (PRINCIPLES_DIR / f"{event_type}.yaml").exists()
        if not yaml_exists:
            return {
                "action_type": "new_yaml_shadow",
                "target": event_type,
                "rationale": (
                    f"Event '{event_type}' déclenché {frequency}x en {window_hours}h "
                    "sans YAML de principe correspondant — candidat pour un nouveau "
                    "principe SHADOW (aucune promotion automatique, R25')."
                ),
                "confidence": round(min(0.5 + frequency / 1000, 0.95), 2),
            }
        return {
            "action_type": "review_calibration",
            "target": event_type,
            "rationale": (
                f"Event '{event_type}' très fréquent ({frequency}x/{window_hours}h) "
                "avec YAML déjà existant — vérifier la calibration des conditions."
            ),
            "confidence": round(min(0.3 + frequency / 2000, 0.6), 2),
        }

    if pattern_type == "pattern_correction":
        lesson = str(pattern.get("lesson", ""))
        return {
            "action_type": "update_yaml_condition",
            "target": lesson[:120],
            "rationale": (
                f"Correction Søn répétée {frequency}x sur la même leçon — condition "
                "YAML existante probablement mal calibrée, proposition de mise à "
                "jour (validation Søn requise, R25')."
            ),
            "confidence": round(min(0.5 + frequency / 20, 0.9), 2),
        }

    if pattern_type == "pattern_combinaison":
        event_type = pattern.get("event_type", "")
        signature = pattern.get("signature", "")
        return {
            "action_type": "propose_dedicated_agent",
            "target": f"{event_type}::{signature}",
            "rationale": (
                f"Combinaison event_type+payload récurrente ({frequency}x/"
                f"{window_hours}h) — candidat pour un agent dédié sur ce flux."
            ),
            "confidence": round(min(0.4 + frequency / 100, 0.75), 2),
        }

    return {
        "action_type": "none",
        "target": None,
        "rationale": "Pattern non reconnu.",
        "confidence": 0.0,
    }


def learn_cycle(hours: int = 24, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Cycle d'apprentissage complet : scan → propose → publie sur le bus → journal.

    Ne publie que les propositions avec confiance > PROPOSAL_CONFIDENCE_MIN.
    Retourne la liste des propositions publiées.
    """
    patterns = scan_patterns(hours=hours, db_path=db_path)
    proposals: list[dict[str, Any]] = []

    conn = _conn(db_path)
    try:
        for pattern in patterns:
            action = propose_action(pattern)
            if action["confidence"] <= PROPOSAL_CONFIDENCE_MIN:
                continue

            proposal = {**action, "pattern": pattern}
            now_ms = int(time.time() * 1000)

            conn.execute(
                "INSERT INTO agent_event_bus "
                "(ts, producer, event_type, payload, correlation_id) "
                "VALUES (?, 'meta_agent', 'proposal', ?, ?)",
                (
                    now_ms,
                    json.dumps(proposal, ensure_ascii=False),
                    pattern.get("event_type"),
                ),
            )
            conn.execute(
                "INSERT INTO cognitive_journal "
                "(ts, agent, event_type, lessons, metadata) "
                "VALUES (?, 'meta_agent', 'lesson', ?, ?)",
                (
                    now_ms,
                    action["rationale"],
                    json.dumps(pattern, ensure_ascii=False),
                ),
            )
            proposals.append(proposal)
        conn.commit()
    finally:
        conn.close()

    return proposals


def get_proposals(limit: int = 5, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Propositions en attente de validation Søn, triées par confiance décroissante."""
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, ts, payload FROM agent_event_bus "
            "WHERE event_type = 'proposal' AND consumed_by IS NULL "
            "ORDER BY ts DESC"
        ).fetchall()
    finally:
        conn.close()

    proposals: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            continue
        payload["_bus_id"] = row["id"]
        payload["_ts"] = row["ts"]
        proposals.append(payload)

    proposals.sort(key=lambda p: p.get("confidence", 0.0), reverse=True)
    return proposals[:limit]

"""meta_agent.py — META-AGENT V9 (Phase 15, apprentissage autonome).

Chaîne : Bus (core/v9/agent_bus.py, data/v9_agent_bus.db) → [META-AGENT] →
proposals (bus, event_type='proposal') + cognitive_journal.lessons.

Le meta-agent est un CONSOMMATEUR passif du bus : il lit les events non
consommés via `agent_bus.get_pending_events()`, détecte des patterns
récurrents, et PROPOSE des actions — il n'agit jamais lui-même (toute
proposition reste soumise à validation Søn, doctrine R25'). Premier
consommateur du bus (`agent_bus.get_pending_events()` porte déjà la note
« vue globale pour le meta-agent de supervision »).

NOTE — réconciliation : ce module consomme `core/v9/agent_bus.py`
(livré en parallèle sur la même branche, DECISIONS_LOG 2026-07-08
« Agent Bus V9 »), pas un bus maison. Seule `cognitive_journal` (absente
d'agent_bus.py, nécessaire pour tracer les corrections Søn répétées) est
ajoutée ici, sur la même DB (`data/v9_agent_bus.db`, via
`agent_bus.get_connection()`).

Doctrine respectée :
- R8 : 0 modification core/v9/config.py, orchestrator.py,
  principle_engine.py, principles/*.yaml (lecture seule sur ces sources).
  `core/v9/agent_bus.py` n'est pas modifié non plus (consommé via son API
  publique uniquement).
- R18 : zéro LLM, zéro appel réseau — patterns détectés par comptage pur.
- R25' : le meta-agent PROPOSE, il ne PROMEUT ni ne modifie jamais un YAML.
- 0 dépendance pip (stdlib only : sqlite3, json, collections, datetime).
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.v9 import agent_bus
from core.v9.config import PRINCIPLES_DIR

# ── Schéma cognitive_journal (absent d'agent_bus.py, ajouté ici) ───────
SCHEMA_JOURNAL = """
CREATE TABLE IF NOT EXISTS cognitive_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
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

# Bornage pratique : get_pending_events() n'a pas de filtre temporel natif,
# on sur-fetch puis on filtre côté client sur `hours`.
_MAX_EVENTS_FETCH = 100_000


def _journal_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Connexion sur la DB du bus (data/v9_agent_bus.db) + table journal garantie."""
    conn = agent_bus.get_connection(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_JOURNAL)
    conn.commit()
    return conn


def _log_lesson(rationale: str, pattern: dict[str, Any], db_path: Path | None = None) -> None:
    """Log une leçon apprise dans cognitive_journal."""
    conn = _journal_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO cognitive_journal (ts, agent, event_type, lessons, metadata) "
            "VALUES (?, 'meta_agent', 'lesson', ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                rationale,
                json.dumps(pattern, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _payload_signature(payload: Any) -> str:
    """Signature stable d'un payload pour regrouper les combinaisons similaires."""
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
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    events = agent_bus.get_pending_events(limit=_MAX_EVENTS_FETCH, db_path=db_path)
    events = [e for e in events if e.get("created_at", "") >= cutoff_iso]

    patterns: list[dict[str, Any]] = []

    type_counts = Counter(e["event_type"] for e in events)
    for event_type, count in type_counts.items():
        if count > FREQUENT_THRESHOLD:
            patterns.append({
                "pattern_type": "pattern_frequent",
                "event_type": event_type,
                "frequency": count,
                "window_hours": hours,
            })

    combo_counts = Counter(
        (e["event_type"], _payload_signature(e.get("payload"))) for e in events
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

    conn = _journal_conn(db_path)
    try:
        correction_rows = conn.execute(
            "SELECT lessons FROM cognitive_journal "
            "WHERE event_type = 'correction' AND ts >= ?",
            (cutoff_iso,),
        ).fetchall()
    finally:
        conn.close()
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

    for pattern in patterns:
        action = propose_action(pattern)
        if action["confidence"] <= PROPOSAL_CONFIDENCE_MIN:
            continue

        proposal = {**action, "pattern": pattern}
        agent_bus.publish(
            event_type="proposal",
            source="meta_agent",
            payload=proposal,
            db_path=db_path,
        )
        _log_lesson(action["rationale"], pattern, db_path=db_path)
        proposals.append(proposal)

    return proposals


def get_proposals(limit: int = 5, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Propositions en attente de validation Søn, triées par confiance décroissante."""
    events = agent_bus.get_pending_events(limit=_MAX_EVENTS_FETCH, db_path=db_path)

    proposals: list[dict[str, Any]] = []
    for e in events:
        if e.get("event_type") != "proposal":
            continue
        payload = e.get("payload")
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        payload["_bus_id"] = e["id"]
        payload["_ts"] = e["created_at"]
        proposals.append(payload)

    proposals.sort(key=lambda p: p.get("confidence", 0.0), reverse=True)
    return proposals[:limit]

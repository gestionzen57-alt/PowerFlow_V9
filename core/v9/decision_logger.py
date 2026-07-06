"""DecisionLogger — couche Décision (Phase 9) PowerFlow V9.

Chaîne cognitive étendue :
    ... → Exploitabilité → Principes → Signal → [DÉCISION]

Persiste le contexte complet d'une décision (signal + scène +
comportement + fenêtre + exploitabilité + régime + principes) pour
permettre un replay intégral — aucune logique d'exécution d'ordre.
`action` est une recommandation qualitative, jamais un ordre : observer
/ surveiller / preparer_entree / aucune_action.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH, SCHEMA_VERSION
from core.v9.db_schema import get_connection
from core.v9.decision_db import DECISIONS_COLUMNS, init_decision_db

ACTIONS = {"observer", "surveiller", "preparer_entree", "aucune_action"}


class DecisionLoggerError(ValueError):
    """Erreur de journalisation de décision (signal introuvable)."""


class DecisionLogger:
    """Assemble et persiste une décision (contexte complet, replayable)."""

    def __init__(self, db_path: Path | str | None = None, source_type: str = "live") -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.source_type = source_type
        init_decision_db(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_signal(self, conn: sqlite3.Connection, snapshot_id: str) -> sqlite3.Row:
        """Charge le signal « porteur de décision » pour un snapshot.

        Tri par pertinence décisionnelle, pas par simple timestamp :
        un signal directionnel+exploitable est intrinsèquement plus
        informatif qu'un signal non-exploitable (raison_absence posé).
        On priorise donc les signaux directionnels, puis on prend le
        plus récent (ORDER BY id DESC) en cas d'ex-aequo.

        Bug fixé 2026-07-06 (pre-correction : ORDER BY id DESC LIMIT 1
        prenait le DERNIER signal inséré pour un snapshot, même si
        non-directionnel ; un signal directionnel généré APRÈS une
        première décision figée restait invisible pour DecisionLogger).
        """
        row = conn.execute(
            """
            SELECT * FROM signals
            WHERE snapshot_id = ?
            ORDER BY
                (direction IS NOT NULL AND direction != 'neutre'
                 AND exploitability_statut != 'non_exploitable') DESC,
                id DESC
            LIMIT 1
            """,
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise DecisionLoggerError(f"aucun signal journalise pour snapshot {snapshot_id!r}")
        return row

    def _load_chain(self, conn: sqlite3.Connection, snapshot_id: str) -> dict[str, Any]:
        scene = conn.execute(
            "SELECT * FROM scenes WHERE forces_snapshot_ref = ? ORDER BY id DESC LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        behavior = window = exploitability = None
        if scene is not None:
            behavior = conn.execute(
                "SELECT * FROM behaviors WHERE scene_id_ref = ? ORDER BY id DESC LIMIT 1",
                (scene["scene_id"],),
            ).fetchone()
        if behavior is not None:
            window = conn.execute(
                "SELECT * FROM windows WHERE behavior_id = ? ORDER BY id DESC LIMIT 1",
                (behavior["behavior_id"],),
            ).fetchone()
        if window is not None:
            exploitability = conn.execute(
                "SELECT * FROM exploitability WHERE window_id = ? ORDER BY id DESC LIMIT 1",
                (window["window_id"],),
            ).fetchone()
        return {
            "scene": dict(scene) if scene else None,
            "behavior": dict(behavior) if behavior else None,
            "window": dict(window) if window else None,
            "exploitability": dict(exploitability) if exploitability else None,
        }

    def _load_regime(self, conn: sqlite3.Connection, snapshot_id: str) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM regime_snapshots WHERE forces_snapshot_ref = ?", (snapshot_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def _load_principles(self, conn: sqlite3.Connection, snapshot_id: str) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM principle_evaluations WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def _determine_action(self, signal: sqlite3.Row, exploitability: dict | None) -> str:
        if signal["raison_absence"] is not None or signal["direction"] in (None, "neutre"):
            return "aucune_action"
        statut = exploitability["statut"] if exploitability else None
        if statut == "exploitable" and signal["horizon"] == "court_terme":
            return "preparer_entree"
        if statut in ("exploitable", "watchlist"):
            return "surveiller"
        return "observer"

    def log(self, snapshot_id: str) -> dict[str, Any]:
        """Assemble et persiste la décision pour un snapshot (le signal
        associé doit déjà avoir été journalisé par SignalGenerator)."""
        conn = self._connect()
        try:
            signal = self._load_signal(conn, snapshot_id)
            chain = self._load_chain(conn, snapshot_id)
            regime = self._load_regime(conn, snapshot_id)
            principles = self._load_principles(conn, snapshot_id)

            action = self._determine_action(signal, chain["exploitability"])

            decision = {
                "decision_id": _decision_id_for_snapshot(snapshot_id),
                "schema_version": SCHEMA_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "snapshot_id": snapshot_id,
                "signal_id": signal["signal_id"],
                "action": action,
                "symbol": signal["symbol"],
                "timeframe": signal["timeframe"],
                "currency": signal["currency"],
                "scene_id": chain["scene"]["scene_id"] if chain["scene"] else None,
                "behavior_id": chain["behavior"]["behavior_id"] if chain["behavior"] else None,
                "window_id": chain["window"]["window_id"] if chain["window"] else None,
                "exploitability_id": signal["exploitability_id"],
                "regime_type": signal["regime_type"],
                "direction": signal["direction"],
                "confiance": signal["confiance"],
                "principes": sorted(set(json.loads(signal["principes_source_json"] or "[]"))),
                "source_type": self.source_type,
                "contexte_complet": {
                    "signal": dict(signal),
                    "scene": chain["scene"],
                    "behavior": chain["behavior"],
                    "window": chain["window"],
                    "exploitability": chain["exploitability"],
                    "regime": regime,
                    "principle_evaluations": principles,
                },
            }

            self._write_to_db(conn, decision)
            return decision
        finally:
            conn.close()

    def _write_to_db(self, conn: sqlite3.Connection, decision: dict) -> None:
        """INSERT idempotent par snapshot_id.

        Avant l'INSERT, cherche une décision existante pour le même
        snapshot_id. Si elle existe ET que la nouvelle décision est de
        meilleure qualité décisionnelle, on l'écrase par INSERT OR REPLACE
        sur decision_id (UNIQUE existant, déterministe depuis snapshot_id).
        Sinon (ancienne déjà directionnelle ou qualité équivalente), skip.

        Critère de qualité (du meilleur au moins bon) :
          1. directionnelle + court_terme  (action ∈ {preparer_entree,
             surveiller})
          2. directionnelle                (action=observer)
          3. non_directionnelle            (action=aucune_action)

        Bug fixé 2026-07-06 : avant le fix, decision_id était
        timestamp+uuid (changement à chaque appel), donc INSERT OR REPLACE
        créait une nouvelle rangée à chaque rejeu (3697 → 3960 sur 3
        snapshots rejoués). Maintenant, decision_id est stable par
        snapshot_id (cf. _generate_decision_id), et le pré-check qualité
        évite d'écraser une bonne décision par une mauvaise.
        """
        now = datetime.now(timezone.utc).isoformat()
        values = {
            **decision,
            "principes_json": json.dumps(decision["principes"], ensure_ascii=False),
            "contexte_complet_json": json.dumps(decision["contexte_complet"], ensure_ascii=False, default=str),
            "created_at": now,
        }
        # Pré-check qualité : si une décision existe déjà et est meilleure
        # ou égale, on skip l'écriture pour préserver l'idempotence.
        existing_row = conn.execute(
            "SELECT direction, action, confiance FROM decisions WHERE snapshot_id = ?",
            (decision["snapshot_id"],),
        ).fetchone()
        if existing_row is not None:
            existing_quality = _action_quality(
                existing_row["direction"], existing_row["action"], existing_row["confiance"]
            )
            new_quality = _action_quality(
                decision["direction"], decision["action"], decision["confiance"]
            )
            # Nouvelle qualité strictement supérieure → on écrase.
            # Sinon → on garde l'ancien (skip silencieux).
            if new_quality <= existing_quality:
                return

        columns = ", ".join(DECISIONS_COLUMNS)
        placeholders = ", ".join("?" for _ in DECISIONS_COLUMNS)
        conn.execute(
            f"INSERT OR REPLACE INTO decisions ({columns}) VALUES ({placeholders})",
            [values[c] for c in DECISIONS_COLUMNS],
        )
        conn.commit()


def _action_quality(direction: str | None, action: str, confiance: int | None) -> int:
    """Score entier de qualité décisionnelle.

    Permet l'idempotence ordonnée : si une décision 'aucune_action'
    existe déjà pour un snapshot, un rejeu qui produit aussi 'aucune_action'
    sera ignoré. Un rejeu qui produit une décision directionnelle
    écrasera l'ancienne 'aucune_action' (cas emblématique bug session 2).

    Échelle (du moins bon au meilleur) :
      0 → aucune_action (non directionnelle)
      1 → observer       (directionnelle mais passive)
      2 → surveiller     (directionnelle + watchlist)
      3 → preparer_entree (directionnelle + exploitable + court terme)
    """
    if direction is None or direction == "neutre":
        return 0
    if action == "preparer_entree":
        return 3
    if action == "surveiller":
        return 2
    if action == "observer":
        return 1
    return 0


def _decision_id_for_snapshot(snapshot_id: str) -> str:
    """decision_id déterministe par snapshot_id.

    Avant 2026-07-06 : timestamp+uuid → unique par appel → INSERT OR
    REPLACE créait une nouvelle rangée à chaque rejeu (3697 → 3960 sur
    3 snapshots rejoués).

    Maintenant : hash court de snapshot_id (12 chars hex, suffisant pour
    l'unicité au sein d'une session). 2 appels .log() sur le même
    snapshot produisent le même decision_id → INSERT OR REPLACE écrase
    vraiment.

    Idempotence par snapshot_id garantie côté DB (UNIQUE constraint
    existante sur decision_id).
    """
    short = uuid.uuid5(uuid.NAMESPACE_URL, snapshot_id).hex[:12]
    return f"dec_{short}"


def _generate_decision_id(symbol: str, timeframe: str) -> str:
    """Compatibilité historique — ne plus utiliser en V9.

    Conservée pour ne pas casser d'imports legacy. Retourne désormais
    un decision_id basé sur (symbol, timeframe) mais ce n'est PAS
    idempotent au niveau snapshot_id. Préférez _decision_id_for_snapshot.
    """
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"dec_{compact_ts}_{symbol.lower()}_{timeframe.lower()}_{uuid.uuid4().hex[:6]}"

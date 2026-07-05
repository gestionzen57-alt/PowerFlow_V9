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

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        init_decision_db(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_signal(self, conn: sqlite3.Connection, snapshot_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM signals WHERE snapshot_id = ? ORDER BY id DESC LIMIT 1",
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
                "decision_id": _generate_decision_id(signal["symbol"], signal["timeframe"]),
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
        now = datetime.now(timezone.utc).isoformat()
        values = {
            **decision,
            "principes_json": json.dumps(decision["principes"], ensure_ascii=False),
            "contexte_complet_json": json.dumps(decision["contexte_complet"], ensure_ascii=False, default=str),
            "created_at": now,
        }
        columns = ", ".join(DECISIONS_COLUMNS)
        placeholders = ", ".join("?" for _ in DECISIONS_COLUMNS)
        conn.execute(
            f"INSERT OR REPLACE INTO decisions ({columns}) VALUES ({placeholders})",
            [values[c] for c in DECISIONS_COLUMNS],
        )
        conn.commit()


def _generate_decision_id(symbol: str, timeframe: str) -> str:
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"dec_{compact_ts}_{symbol.lower()}_{timeframe.lower()}_{uuid.uuid4().hex[:6]}"

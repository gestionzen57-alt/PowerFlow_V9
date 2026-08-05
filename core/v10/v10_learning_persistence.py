"""V10 Learning Persistence — persiste/recharge l'état d'apprentissage (Phase R).

Le modèle d'apprentissage (état ErrorLearner : n_trades, n_wins, per_setup,
lessons, drift) est persisté dans une table SQLite `v10_learning_state` pour
être rechargé entre les sessions et les runs. L'apprentissage est ainsi
CONTINU même en replay et à travers les redémarrages.

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7, R9 audit sérialisable,
R10 zéro ordre réel (persistance de métadonnées, pas d'ordres).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS v10_learning_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE,
    payload_json TEXT,
    updated_at TEXT
);
"""


class LearningPersistence:
    """Persistance de l'état d'apprentissage (ErrorLearner + lessons)."""

    def __init__(self, db_path: str = "data/v10_learning_state.db"):
        self.db_path = db_path
        self._mem: Optional[Dict[str, str]] = {}
        self._conn = None
        try:
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
            self._conn = sqlite3.connect(db_path)
            self._conn.execute(SCHEMA)
            self._conn.commit()
            self._mem = None
        except Exception as exc:
            log.warning("SQLite indisponible, fallback in-memory (R6): %s", exc)
            self._conn = None
            self._mem = {}

    def save_state(self, key: str, state: Dict) -> None:
        """Persiste un dict d'état (ErrorLearner.as_dict, lessons, etc)."""
        payload = json.dumps(state, ensure_ascii=False, default=str)
        now = datetime.now(timezone.utc).isoformat()
        if self._conn is not None:
            try:
                self._conn.execute(
                    "INSERT INTO v10_learning_state (key, payload_json, updated_at) "
                    "VALUES (?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET payload_json=?, updated_at=?",
                    (key, payload, now, payload, now),
                )
                self._conn.commit()
            except Exception as exc:
                log.warning("save_state échoué (R6): %s", exc)
        elif self._mem is not None:
            self._mem[key] = payload

    def load_state(self, key: str) -> Dict:
        """Recharge un état persisté. Retourne {} si absent (R6 fail-open)."""
        if self._conn is not None:
            try:
                row = self._conn.execute(
                    "SELECT payload_json FROM v10_learning_state WHERE key=?",
                    (key,),
                ).fetchone()
                if row:
                    return json.loads(row[0])
                return {}
            except Exception as exc:
                log.warning("load_state échoué (R6): %s", exc)
                return {}
        raw = (self._mem or {}).get(key)
        return json.loads(raw) if raw else {}

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass


def learner_to_dict(learner) -> Dict:
    """Convertit un ErrorLearner en dict persistable (R9)."""
    return {
        "n_trades": learner.state.n_trades,
        "n_wins": learner.state.n_wins,
        "n_losses": learner.state.n_losses,
        "current_streak": learner.state.current_streak,
        "max_losing_streak": learner.state.max_losing_streak,
        "drift_detected": learner.state.drift_detected,
        "drift_count": learner.state.drift_count,
        "recalibrate_recommended": learner.state.recalibrate_recommended,
        "recalibrate_setups": learner.state.recalibrate_setups,
        "per_setup": learner.state.per_setup,
        "lessons": learner.state.lessons,
    }


def dict_to_learner(data: Dict, learner=None):
    """Restore un ErrorLearner depuis un dict persisté (additif)."""
    from core.v10.v10_error_learner import ErrorLearner, ErrorLearnerState

    lr = learner or ErrorLearner()
    st = lr.state
    st.n_trades = int(data.get("n_trades", 0))
    st.n_wins = int(data.get("n_wins", 0))
    st.n_losses = int(data.get("n_losses", 0))
    st.current_streak = int(data.get("current_streak", 0))
    st.max_losing_streak = int(data.get("max_losing_streak", 0))
    st.drift_detected = bool(data.get("drift_detected", False))
    st.drift_count = int(data.get("drift_count", 0))
    st.recalibrate_recommended = bool(data.get("recalibrate_recommended", False))
    st.recalibrate_setups = list(data.get("recalibrate_setups", []))
    st.per_setup = dict(data.get("per_setup", {}))
    st.lessons = list(data.get("lessons", []))
    return lr


__all__ = [
    "LearningPersistence",
    "learner_to_dict",
    "dict_to_learner",
]

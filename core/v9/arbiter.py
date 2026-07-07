"""Arbiter — consolidation des décisions V9 pour paper-trade (Phase 10).

Doctrine : lecture seule sur la table `decisions`. Aucune écriture en DB.
L'Arbiter consolide les décisions d'un même snapshot en une seule
synthèse directionnelle (direction majoritaire + confiance moyenne),
utilisée ensuite par RiskManager (filtre) puis PaperTradeLogger (saisie).

Aucune logique d'exécution d'ordre — la doctrine interdit tout ordre
réel avant Phase 12. Ce module ne fait QUE consolider des décisions déjà
journalisées.

Usage :
    arbiter = Arbiter()
    result = arbiter.consolidate(snapshot_id)
    # → dict direction / confiance_arbitree / principes_source /
    #   nb_principes_actifs / timestamp / arbiter_version
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection

ARBITER_VERSION = "1.0"

# Plafond confiance si < 2 principes actifs (force le filtre risk_manager).
CONFIANCE_PLAFOND_SOUS_2_PRINCIPES = 74


class ArbiterError(ValueError):
    """Erreur de l'Arbiter (snapshot introuvable, données invalides)."""


class Arbiter:
    """Consolide les décisions d'un snapshot_id en une synthèse unique."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_decisions(self, conn: sqlite3.Connection, snapshot_id: str) -> list[dict]:
        rows = conn.execute(
            "SELECT decision_id, direction, confiance, principes_json, timestamp "
            "FROM decisions "
            "WHERE snapshot_id = ? AND source_type = 'live' "
            "AND direction IS NOT NULL AND direction != 'neutre'",
            (snapshot_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _extract_principes(principes_json: str | None) -> list[str]:
        if not principes_json:
            return []
        try:
            data = json.loads(principes_json)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(data, list):
            return []
        return [p for p in data if isinstance(p, str)]

    def consolidate(self, snapshot_id: str) -> dict:
        """Consolide les décisions d'un snapshot en une synthèse unique.

        Logique :
        - Lecture de toutes les décisions `live` directionnelles pour
          ce snapshot_id.
        - Si vide → direction='neutre', confiance=0.
        - Sinon → direction majoritaire, confiance=moyenne des confiances
          dans la direction majoritaire, principes_source=union des
          principes déclenchés dans cette direction.
        - Si nb_principes_actifs < 2 → confiance_arbitree plafonnée à 74.
        """
        conn = self._connect()
        try:
            rows = self._load_decisions(conn, snapshot_id)
        finally:
            conn.close()

        if not rows:
            return {
                "direction": "neutre",
                "confiance_arbitree": 0,
                "principes_source": [],
                "nb_principes_actifs": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "arbiter_version": ARBITER_VERSION,
                "snapshot_id": snapshot_id,
                "nb_decisions_consolidees": 0,
            }

        # Direction majoritaire (gestion ex-aequo : Counter.most_common).
        directions = [r["direction"] for r in rows]
        counter = Counter(directions)
        direction_majoritaire, _ = counter.most_common(1)[0]

        # Décisions dans la direction majoritaire uniquement.
        rows_dir = [r for r in rows if r["direction"] == direction_majoritaire]

        # Confiance moyenne (entière, arrondie).
        confiances = [int(r["confiance"]) for r in rows_dir if r["confiance"] is not None]
        confiance_moyenne = round(sum(confiances) / len(confiances)) if confiances else 0

        # Union des principes (set, ordre stable par 1ère apparition).
        seen: set[str] = set()
        principes_union: list[str] = []
        for r in rows_dir:
            for p in self._extract_principes(r["principes_json"]):
                if p not in seen:
                    seen.add(p)
                    principes_union.append(p)

        nb_principes_actifs = len(principes_union)

        # Plafond confiance si < 2 principes actifs.
        confiance_finale = confiance_moyenne
        plafonne = False
        if nb_principes_actifs < 2:
            confiance_finale = min(confiance_finale, CONFIANCE_PLAFOND_SOUS_2_PRINCIPES)
            plafonne = confiance_finale != confiance_moyenne

        # Timestamp le plus récent parmi les décisions consolidées.
        timestamps = [r["timestamp"] for r in rows_dir if r["timestamp"]]
        ts_max = max(timestamps) if timestamps else datetime.now(timezone.utc).isoformat()

        return {
            "direction": direction_majoritaire,
            "confiance_arbitree": int(confiance_finale),
            "confiance_brute": int(confiance_moyenne),
            "plafonne_sous_2_principes": plafonne,
            "principes_source": principes_union,
            "nb_principes_actifs": nb_principes_actifs,
            "timestamp": ts_max,
            "arbiter_version": ARBITER_VERSION,
            "snapshot_id": snapshot_id,
            "nb_decisions_consolidees": len(rows_dir),
            "nb_decisions_totales": len(rows),
        }
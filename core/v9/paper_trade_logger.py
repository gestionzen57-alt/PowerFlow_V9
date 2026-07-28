"""PaperTradeLogger — ouverture / clôture paper-trades V9 (Phase 9.7).

Doctrine : simulation uniquement. Aucune logique d'exécution d'ordre
avant Phase 12 (interdit fondateur). Ce logger enregistre les
paper-trades dans la table `paper_trades` (cf. paper_trades_db.py) à
partir d'une sortie Arbiter validée par RiskManager.

Workflow type :
    arbiter_result = Arbiter().consolidate(snapshot_id)
    risk_result = RiskManager().evaluate(arbiter_result, context)
    if risk_result["go"]:
        trade_id = PaperTradeLogger().log_open(arbiter_result, context)
        # ... plus tard ...
        PaperTradeLogger().log_close(trade_id, pips_simulated=12.5)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection
from core.v9.paper_trades_db import init_paper_trades_db


class PaperTradeLoggerError(ValueError):
    """Erreur PaperTradeLogger (trade introuvable, déjà clos, etc.)."""


class PaperTradeLogger:
    """Logger des paper-trades V9 (Phase 10). Lecture + écriture."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        init_paper_trades_db(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _generate_trade_id(self) -> str:
        return f"pt_{uuid.uuid4().hex[:12]}"

    def _normalize_principes_source(self, arbiter_result: dict) -> list[str]:
        """Normalise principes_source depuis arbiter_result (liste de strings)."""
        ps = arbiter_result.get("principes_source") or []
        if not isinstance(ps, list):
            return []
        return [p for p in ps if isinstance(p, str)]

    def log_open(
        self,
        arbiter_result: dict,
        context: dict | None = None,
        *,
        trade_id: str | None = None,
    ) -> str:
        """Ouvre un paper-trade et retourne son trade_id.

        trade_id optionnel - genere automatiquement si None (utile pour
        les tests d'idempotence).

        Additif (R2) : le sizing_factor peut etre passe via context["sizing_factor"].
        Si present, il est stocke dans la base pour reutilisation par le runner live.
        Le pyramiding du trade_engine est multiplie par ce facteur pour le live.
        """
        if not isinstance(arbiter_result, dict):
            raise PaperTradeLoggerError(
                f"arbiter_result doit être un dict, reçu : {type(arbiter_result).__name__}"
            )
        snapshot_id = arbiter_result.get("snapshot_id")
        if not snapshot_id:
            raise PaperTradeLoggerError(
                "arbiter_result doit contenir 'snapshot_id' (non vide)"
            )
        direction = arbiter_result.get("direction")
        if direction not in ("haussiere", "baissiere"):
            raise PaperTradeLoggerError(
                f"direction invalide pour paper-trade : {direction!r} "
                "(attendu: 'haussiere' ou 'baissiere')"
            )
        confiance = int(arbiter_result.get("confiance_arbitree", 0) or 0)

        if trade_id is None:
            trade_id = self._generate_trade_id()

        opened_at = datetime.now(timezone.utc).isoformat()
        principes = self._normalize_principes_source(arbiter_result)
        # Additif R2 : sizing_factor (pyramiding boost) injecte par trade_engine
        # section 5 motion CEO 28/07. Stocke dans context pour reutilisation runner live.
        if context and "sizing_factor" in context:
            # Keep the existing context but ensure sizing_factor survives JSON
            pass
        context_json = json.dumps(
            context or {}, ensure_ascii=False, default=str
        )

        principes_json = json.dumps(principes, ensure_ascii=False)

        conn = self._connect()
        try:
            # Motion #32 : idempotence. Un même (snapshot_id, direction,
            # principes_source) = une même décision → un seul paper-trade.
            # ON CONFLICT DO NOTHING (index unique idx_pt_snap_dir_princ) évite
            # la re-duplication à la ré-résolution ; on renvoie le trade_id
            # canonique existant plutôt qu'un id fantôme non inséré.
            cur = conn.execute(
                "INSERT INTO paper_trades ("
                " trade_id, snapshot_id, direction, confiance,"
                " principes_source, opened_at, closed_at,"
                " pips_simulated, is_win, risk_go_context"
                ") VALUES (?,?,?,?,?,?,NULL,NULL,NULL,?)"
                " ON CONFLICT(snapshot_id, direction, principes_source)"
                " DO NOTHING",
                (
                    trade_id, snapshot_id, direction, confiance,
                    principes_json, opened_at, context_json,
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                existing = conn.execute(
                    "SELECT trade_id FROM paper_trades"
                    " WHERE snapshot_id = ? AND direction = ?"
                    "   AND principes_source = ?"
                    " ORDER BY opened_at LIMIT 1",
                    (snapshot_id, direction, principes_json),
                ).fetchone()
                if existing is not None:
                    return existing["trade_id"]
        finally:
            conn.close()

        return trade_id

    def log_close(self, trade_id: str, pips_simulated: float) -> None:
        """Clôture un paper-trade : closed_at, pips_simulated, is_win.

        is_win = 1 si pips > 0, 0 sinon. Refuse de fermer un trade déjà
        clos (closed_at NOT NULL).
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT closed_at FROM paper_trades WHERE trade_id = ?",
                (trade_id,),
            ).fetchone()
            if row is None:
                raise PaperTradeLoggerError(
                    f"trade_id introuvable : {trade_id!r}"
                )
            if row["closed_at"] is not None:
                raise PaperTradeLoggerError(
                    f"trade {trade_id!r} déjà clos à {row['closed_at']!r} "
                    "(impossible de re-clôturer)"
                )

            closed_at = datetime.now(timezone.utc).isoformat()
            is_win = 1 if pips_simulated > 0 else 0

            conn.execute(
                "UPDATE paper_trades SET closed_at = ?, pips_simulated = ?, "
                "is_win = ? WHERE trade_id = ?",
                (closed_at, pips_simulated, is_win, trade_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_trade(self, trade_id: str) -> dict[str, Any] | None:
        """Lit un trade (utile aux tests et au dashboard)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM paper_trades WHERE trade_id = ?",
                (trade_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
"""SignalGenerator — couche Décision (Phase 9) PowerFlow V9.

Chaîne cognitive étendue :
    ... → Exploitabilité → Principes → [SIGNAL] → Décision

Agrège les évaluations de principes ACTIVE (jamais SHADOW — même
sémantique que le "shadow gate" V8 : un principe SHADOW est journalisé
et calibré, jamais routé vers un signal) en un signal directionnel pour
le symbole du snapshot. Suit la même convention que `forces_reader.py` :
la direction se lit sur la devise de BASE du symbole (ex. GBP pour
GBPUSD) ; la devise de contrepartie (quote) sert de corroboration.

« Absence de signal » est une réponse de première classe (charte
cognitive V9, même principe que « non exploitable »/« refusé » en
couche Exploitabilité) : toujours journalisée avec sa raison, jamais
omise silencieusement.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import (
    DB_PATH,
    REGIMES_INADEQUATS,
    SCHEMA_VERSION,
    SIGNAL_CONFIANCE_HORIZON_COURT,
)
from core.v9.db_schema import get_connection
from core.v9.signal_db import SIGNALS_COLUMNS, init_signal_db

STATUS_ACTIVE = "ACTIVE"


class SignalGeneratorError(ValueError):
    """Erreur de génération de signal (snapshot introuvable, symbole invalide)."""


@dataclass
class SymbolCurrencies:
    base: str
    quote: str

    @classmethod
    def from_symbol(cls, symbol: str) -> "SymbolCurrencies":
        if not symbol or len(symbol) < 6:
            raise SignalGeneratorError(f"symbole invalide pour derivation devise base/quote: {symbol!r}")
        return cls(base=symbol[:3].upper(), quote=symbol[3:6].upper())


class SignalGenerator:
    """Agrège les principes ACTIVE déclenchés en un signal, filtré par
    exploitabilité et régime de marché."""

    def __init__(self, db_path: Path | str | None = None, config: dict | None = None, source_type: str = "live") -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.source_type = source_type
        init_signal_db(self.db_path)
        cfg = dict(config) if config else {}
        self.regimes_inadequats = set(cfg.get("regimes_inadequats", REGIMES_INADEQUATS))
        self.confiance_horizon_court = cfg.get("confiance_horizon_court", SIGNAL_CONFIANCE_HORIZON_COURT)

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Chargement contexte ────────────────────────────────
    def _load_forces(self, conn: sqlite3.Connection, snapshot_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM forces_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if row is None:
            raise SignalGeneratorError(f"snapshot de forces introuvable: {snapshot_id!r}")
        return row

    def _load_exploitability(self, conn: sqlite3.Connection, snapshot_id: str) -> sqlite3.Row | None:
        scene = conn.execute(
            "SELECT scene_id FROM scenes WHERE forces_snapshot_ref = ? ORDER BY id DESC LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        if scene is None:
            return None
        behavior = conn.execute(
            "SELECT behavior_id FROM behaviors WHERE scene_id_ref = ? ORDER BY id DESC LIMIT 1",
            (scene["scene_id"],),
        ).fetchone()
        if behavior is None:
            return None
        window = conn.execute(
            "SELECT window_id FROM windows WHERE behavior_id = ? ORDER BY id DESC LIMIT 1",
            (behavior["behavior_id"],),
        ).fetchone()
        if window is None:
            return None
        return conn.execute(
            "SELECT * FROM exploitability WHERE window_id = ? ORDER BY id DESC LIMIT 1",
            (window["window_id"],),
        ).fetchone()

    def _load_regime_type(self, conn: sqlite3.Connection, snapshot_id: str, currency: str) -> str | None:
        row = conn.execute(
            "SELECT regime_type FROM regime_snapshots WHERE forces_snapshot_ref = ? AND currency = ?",
            (snapshot_id, currency),
        ).fetchone()
        return row["regime_type"] if row else None

    def _load_triggered_active_principles(
        self, conn: sqlite3.Connection, snapshot_id: str, currency: str
    ) -> list[sqlite3.Row]:
        return conn.execute(
            "SELECT * FROM principle_evaluations WHERE snapshot_id = ? AND currency = ? "
            "AND v9_status = ? AND triggered = 1",
            (snapshot_id, currency, STATUS_ACTIVE),
        ).fetchall()

    # ── Génération ─────────────────────────────────────────
    def generate(self, snapshot_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            forces = self._load_forces(conn, snapshot_id)
            symbol, timeframe = forces["symbol"], forces["timeframe"]
            currencies = SymbolCurrencies.from_symbol(symbol)

            exploitability = self._load_exploitability(conn, snapshot_id)
            exploitability_statut = exploitability["statut"] if exploitability else None
            exploitability_id = exploitability["exploitability_id"] if exploitability else None

            regime_type = self._load_regime_type(conn, snapshot_id, currencies.base)

            raison_absence = self._determine_absence_reason(exploitability_statut, regime_type)

            triggered: list[sqlite3.Row] = []
            if raison_absence is None:
                triggered = list(self._load_triggered_active_principles(conn, snapshot_id, currencies.base))
                triggered += list(self._load_triggered_active_principles(conn, snapshot_id, currencies.quote))
                if not triggered:
                    raison_absence = "aucun_principe_actif_declenche"

            if raison_absence is not None:
                signal = self._build_absent_signal(
                    snapshot_id, symbol, timeframe, currencies, regime_type,
                    exploitability_id, exploitability_statut, raison_absence, bool(forces["stale"]),
                )
            else:
                signal = self._build_active_signal(
                    snapshot_id, symbol, timeframe, currencies, regime_type,
                    exploitability_id, exploitability_statut, triggered, bool(forces["stale"]),
                )

            self._write_to_db(conn, signal)
            return signal
        finally:
            conn.close()

    def _determine_absence_reason(
        self, exploitability_statut: str | None, regime_type: str | None
    ) -> str | None:
        if exploitability_statut != "exploitable":
            return f"exploitabilite_non_exploitable:{exploitability_statut or 'absente'}"
        if regime_type is None or regime_type in self.regimes_inadequats:
            return f"regime_inadequat:{regime_type or 'inconnu'}"
        return None

    def _build_absent_signal(
        self, snapshot_id, symbol, timeframe, currencies, regime_type,
        exploitability_id, exploitability_statut, raison_absence, stale,
    ) -> dict[str, Any]:
        return {
            "signal_id": _generate_signal_id(symbol, timeframe),
            "schema_version": SCHEMA_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": snapshot_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "currency": currencies.base,
            "direction": None,
            "confiance": 0,
            "horizon": None,
            "principes_source": [],
            "regime_type": regime_type,
            "exploitability_id": exploitability_id,
            "exploitability_statut": exploitability_statut,
            "raison_absence": raison_absence,
            "stale": stale,
            "source_type": self.source_type,
        }

    def _build_active_signal(
        self, snapshot_id, symbol, timeframe, currencies, regime_type,
        exploitability_id, exploitability_statut, triggered, stale,
    ) -> dict[str, Any]:
        directions = [row["direction"] for row in triggered if row["direction"]]
        vote = Counter(directions)
        if not vote:
            direction = "neutre"
        else:
            top_count = max(vote.values())
            leaders = [d for d, c in vote.items() if c == top_count]
            direction = leaders[0] if len(leaders) == 1 else "neutre"

        confidences = [row["confidence"] for row in triggered if row["confidence"] is not None]
        confiance = round(sum(confidences) / len(confidences)) if confidences else 0
        confiance = max(0, min(100, confiance))
        horizon = "court_terme" if confiance >= self.confiance_horizon_court else "surveillance"

        return {
            "signal_id": _generate_signal_id(symbol, timeframe),
            "schema_version": SCHEMA_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": snapshot_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "currency": currencies.base,
            "direction": direction,
            "confiance": confiance,
            "horizon": horizon,
            "principes_source": sorted({row["principle_id"] for row in triggered}),
            "regime_type": regime_type,
            "exploitability_id": exploitability_id,
            "exploitability_statut": exploitability_statut,
            "raison_absence": None,
            "stale": stale,
            "source_type": self.source_type,
        }

    def _write_to_db(self, conn: sqlite3.Connection, signal: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        values = {
            **signal,
            "principes_source_json": json.dumps(signal["principes_source"], ensure_ascii=False),
            "created_at": now,
        }
        columns = ", ".join(SIGNALS_COLUMNS)
        placeholders = ", ".join("?" for _ in SIGNALS_COLUMNS)
        conn.execute(
            f"INSERT OR REPLACE INTO signals ({columns}) VALUES ({placeholders})",
            [values[c] for c in SIGNALS_COLUMNS],
        )
        conn.commit()


def _generate_signal_id(symbol: str, timeframe: str) -> str:
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"sig_{compact_ts}_{symbol.lower()}_{timeframe.lower()}_{uuid.uuid4().hex[:6]}"

"""MTFConfirmationEngine — lecture anticipée multi-timeframe (Phase 9, bonus).

Stratégie CEO Søn (audit régime GBPUSD, 2026-07-15) : un timeframe
supérieur (« contexte ») établit la thèse directionnelle (sortie de zone,
cassure), le timeframe courant (« trigger ») la confirme par croisement de
forces ou déséquilibre franc. Sans thèse de contexte = pas de setup ; sans
confirmation trigger = pas d'alignement. `evaluate()` ne décide jamais
seul d'une direction : il ne fait que qualifier l'alignement entre deux
lectures déjà produites par `regime_detector` (thèse) et `forces_reader`
(confirmation), et retourne un `confidence_boost` (+25 aligné / -15 en
conflit / 0 sans contexte) que `signal_generator` applique — jamais un
override de la direction déjà votée par les principes.

R2 (additif) : couche lecture-seule sur des tables déjà peuplées, greffée
dans `orchestrator.py` après `regime_detector`/`zone_detector`, avant
`principle_engine`. R6 : `evaluate()` ne lève jamais — toute erreur
retombe sur `mtf_setup="no_context"`/`confidence_boost=0`.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH, SCHEMA_VERSION, SIGNAL_FORCES_FALLBACK_SPREAD_MIN
from core.v9.db_schema import get_connection
from core.v9.mtf_confirmation_db import MTF_CONFIRMATIONS_COLUMNS, init_mtf_confirmation_db

# TF courant (trigger) -> TF de contexte (thèse). H4/D1 n'ont pas de
# contexte supérieur dans V9 (TIMEFRAMES_CANDLE plafonne à D1).
CONTEXT_TF_MAP = {"M5": "H1", "M15": "H4", "M30": "H4", "H1": "H4"}

# Régimes porteurs d'une thèse directionnelle exploitable par le contexte.
# RETOUR_EQUILIBRE est descriptif (reversal) mais sans direction unique
# fiable -> traité comme absence de contexte pour l'alignement.
THESIS_REGIMES = {"CASSURE", "EXTENSION"}

DIRECTION_FROM_CASSURE = {"UP": "haussiere", "DOWN": "baissiere"}

BOOST_ALIGNED = 25
MALUS_CONFLICT = -15


class MTFConfirmationEngineError(ValueError):
    """Erreur d'évaluation MTF (snapshot introuvable)."""


class MTFConfirmationEngine:
    """Qualifie l'alignement thèse (TF contexte) / confirmation (TF courant)
    pour un snapshot de forces, et persiste le résultat dans
    `mtf_confirmations`."""

    def __init__(self, db_path: Path | str | None = None, source_type: str = "live") -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.source_type = source_type
        init_mtf_confirmation_db(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _find_context_snapshot(
        self, conn: sqlite3.Connection, symbol: str, context_tf: str, current_timestamp: str
    ) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT snapshot_id, timestamp, direction, force_gbp, force_usd, force_eur, "
            "force_jpy, force_cad, force_chf, force_aud, force_nzd, "
            "vitesse, croisement_detecte, croisement_direction "
            "FROM forces_snapshots "
            "WHERE symbol = ? AND timeframe = ? AND timestamp <= ? AND stale = 0 "
            "ORDER BY timestamp DESC LIMIT 1",
            (symbol, context_tf, current_timestamp),
        ).fetchone()

    def _no_context(self, reason: str) -> dict[str, Any]:
        return {
            "mtf_setup": "no_context",
            "context_tf": None,
            "trigger_tf": None,
            "context_thesis": None,
            "trigger_confirmation": None,
            "aligned": False,
            "conflict": False,
            "confidence_boost": 0,
            "direction": None,
            "reason": reason,
            "context_snapshot_ref": None,
        }

    def evaluate(self, snapshot_id: str) -> dict[str, Any]:
        """Évalue l'alignement multi-timeframe pour un snapshot de forces et
        persiste le résultat. Retourne toujours un dict complet, même en
        `no_context` (dégradation gracieuse, jamais d'exception)."""
        conn = self._connect()
        trigger_tf: str | None = None
        symbol: str | None = None
        try:
            current = conn.execute(
                "SELECT * FROM forces_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            if current is None:
                raise MTFConfirmationEngineError(
                    f"snapshot de forces introuvable: {snapshot_id!r}"
                )

            symbol, trigger_tf = current["symbol"], current["timeframe"]
            if not symbol or len(symbol) < 6:
                result = self._no_context("symbole_invalide")
            else:
                context_tf = CONTEXT_TF_MAP.get(trigger_tf)
                if context_tf is None:
                    result = self._no_context(f"pas_de_tf_contexte_pour:{trigger_tf}")
                else:
                    result = self._evaluate_alignment(conn, current, symbol, trigger_tf, context_tf)

            result["trigger_tf"] = result.get("trigger_tf") or trigger_tf
            self._write_to_db(conn, snapshot_id, symbol, result)
            return result
        except MTFConfirmationEngineError:
            raise
        except Exception as exc:  # noqa: BLE001 — R6, dégradation gracieuse
            result = self._no_context(f"erreur_evaluation:{exc}")
            result["trigger_tf"] = trigger_tf
            return result
        finally:
            conn.close()

    def _evaluate_alignment(
        self,
        conn: sqlite3.Connection,
        current: sqlite3.Row,
        symbol: str,
        trigger_tf: str,
        context_tf: str,
    ) -> dict[str, Any]:
        base, quote = symbol[:3].upper(), symbol[3:6].upper()

        context_row = self._find_context_snapshot(conn, symbol, context_tf, current["timestamp"])
        if context_row is None:
            result = self._no_context(f"aucun_snapshot_contexte:{context_tf}")
            result["trigger_tf"] = trigger_tf
            result["context_tf"] = context_tf
            return result

        regime_row = conn.execute(
            "SELECT regime_type, cassure_direction FROM regime_snapshots "
            "WHERE forces_snapshot_ref = ? AND currency = ?",
            (context_row["snapshot_id"], base),
        ).fetchone()

        context_thesis = None
        regime_type = regime_row["regime_type"] if regime_row else None
        if regime_row is not None and regime_type in THESIS_REGIMES:
            context_thesis = DIRECTION_FROM_CASSURE.get(regime_row["cassure_direction"])

        # Confirmation TF courant : croisement de forces en priorité (événement
        # discret, cf forces_reader.py), fallback sur le déséquilibre de
        # spread (même seuil/logique que le fallback signal_generator —
        # cohérence inter-couches, pas de second seuil inventé).
        trigger_confirmation = None
        trigger_direction = None
        if current["croisement_detecte"] and current["croisement_direction"]:
            trigger_confirmation = "croisement"
            trigger_direction = current["croisement_direction"]
        else:
            try:
                spread = float(current[f"force_{base.lower()}"]) - float(
                    current[f"force_{quote.lower()}"]
                )
            except (TypeError, KeyError, IndexError):
                spread = 0.0
            if abs(spread) >= SIGNAL_FORCES_FALLBACK_SPREAD_MIN:
                trigger_confirmation = "alignment_spread"
                trigger_direction = "haussiere" if spread > 0 else "baissiere"

        if context_thesis is None or trigger_direction is None:
            result = self._no_context(
                "thesis_absente" if context_thesis is None else "confirmation_absente"
            )
        elif context_thesis == trigger_direction:
            mtf_setup = (
                "sortie_zone_h4_croisement_m15" if regime_type == "CASSURE"
                else "extension_h4_recroisement_m15"
            )
            result = {
                "mtf_setup": mtf_setup,
                "context_thesis": context_thesis,
                "trigger_confirmation": f"{trigger_confirmation}_{trigger_direction}",
                "aligned": True,
                "conflict": False,
                "confidence_boost": BOOST_ALIGNED,
                "direction": trigger_direction,
                "reason": "aligned",
            }
        else:
            result = {
                "mtf_setup": "conflict",
                "context_thesis": context_thesis,
                "trigger_confirmation": f"{trigger_confirmation}_{trigger_direction}",
                "aligned": False,
                "conflict": True,
                "confidence_boost": MALUS_CONFLICT,
                "direction": trigger_direction,
                "reason": "context_trigger_conflict",
            }

        result["trigger_tf"] = trigger_tf
        result["context_tf"] = context_tf
        result["context_snapshot_ref"] = context_row["snapshot_id"]
        return result

    def _write_to_db(
        self, conn: sqlite3.Connection, snapshot_id: str, symbol: str | None, result: dict[str, Any]
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "mtf_id": _generate_mtf_id(symbol or "unknown", result.get("trigger_tf") or "na"),
            "schema_version": SCHEMA_VERSION,
            "timestamp": now,
            "forces_snapshot_ref": snapshot_id,
            "symbol": symbol,
            "trigger_tf": result.get("trigger_tf"),
            "context_tf": result.get("context_tf"),
            "context_snapshot_ref": result.get("context_snapshot_ref"),
            "mtf_setup": result.get("mtf_setup"),
            "context_thesis": result.get("context_thesis"),
            "trigger_confirmation": result.get("trigger_confirmation"),
            "aligned": bool(result.get("aligned")),
            "conflict": bool(result.get("conflict")),
            "confidence_boost": int(result.get("confidence_boost") or 0),
            "direction": result.get("direction"),
            "reason": result.get("reason"),
            "source_type": self.source_type,
            "created_at": now,
        }
        columns = ", ".join(MTF_CONFIRMATIONS_COLUMNS)
        placeholders = ", ".join("?" for _ in MTF_CONFIRMATIONS_COLUMNS)
        conn.execute(
            f"INSERT OR REPLACE INTO mtf_confirmations ({columns}) VALUES ({placeholders})",
            [row[c] for c in MTF_CONFIRMATIONS_COLUMNS],
        )
        conn.commit()


def _generate_mtf_id(symbol: str, trigger_tf: str) -> str:
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"mtf_{compact_ts}_{symbol.lower()}_{trigger_tf.lower()}_{uuid.uuid4().hex[:6]}"

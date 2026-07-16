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
# DIVERSIFY 2026-07-16 (audit lecture multi-dim, Gap 1) : RETOUR_EQUILIBRE
# ajouté. Il représente 47 798 barres (2e régime le plus fréquent) alors que
# CASSURE+EXTENSION ne couvrent que ~0,63 % des barres GBP → le moteur MTF
# était mort (no_context 2052/2053, boost émis 1 seule fois). RETOUR_EQUILIBRE
# porte `cassure_direction=NULL` : sa direction est DÉRIVÉE de la position de
# la force de la devise de base par rapport à l'équilibre (cf. _thesis_direction),
# lecture mean-reversion pure (R18/R25' — décrit, n'invente pas).
THESIS_REGIMES = {"CASSURE", "EXTENSION", "RETOUR_EQUILIBRE"}

DIRECTION_FROM_CASSURE = {"UP": "haussiere", "DOWN": "baissiere"}

# Deadband autour de l'équilibre neutre (50.0) pour dériver la direction de
# réversion d'un RETOUR_EQUILIBRE sans sur-réagir au bruit proche de 50.
NEUTRAL_REFERENCE = 50.0
REVERSION_DEADBAND = 3.0

BOOST_ALIGNED = 25          # boost max (croisement de forces = événement discret fort)
BOOST_ALIGNED_SPREAD_MIN = 12  # plancher pour un alignement par spread (plus faible)
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
            context_thesis = _thesis_direction(
                regime_type, regime_row["cassure_direction"], context_row, base
            )

        # Confirmation TF courant : croisement de forces en priorité (événement
        # discret, cf forces_reader.py), fallback sur le déséquilibre de
        # spread (même seuil/logique que le fallback signal_generator —
        # cohérence inter-couches, pas de second seuil inventé).
        trigger_confirmation = None
        trigger_direction = None
        spread_abs = 0.0
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
                spread_abs = abs(spread)

        if context_thesis is None or trigger_direction is None:
            result = self._no_context(
                "thesis_absente" if context_thesis is None else "confirmation_absente"
            )
        elif context_thesis == trigger_direction:
            mtf_setup = _mtf_setup_label(regime_type)
            # DIVERSIFY 2026-07-16 (Gap 9) — boost PONDÉRÉ par la force de la
            # confluence, plus un +25 aveugle : un croisement de forces
            # (événement discret fort) garde le boost max ; un simple
            # alignement de spread est proportionnel à l'ampleur du spread
            # au-delà du seuil (plancher BOOST_ALIGNED_SPREAD_MIN). Les cas de
            # test historiques (croisement) restent à +25 → non-régression.
            boost = _confluence_boost(trigger_confirmation, spread_abs)
            result = {
                "mtf_setup": mtf_setup,
                "context_thesis": context_thesis,
                "trigger_confirmation": f"{trigger_confirmation}_{trigger_direction}",
                "aligned": True,
                "conflict": False,
                "confidence_boost": boost,
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


def _thesis_direction(
    regime_type: str, cassure_direction: str | None, context_row: Any, base: str
) -> str | None:
    """Dérive la direction de la thèse portée par le TF de contexte.

    - CASSURE / EXTENSION : direction discrète de la cassure (UP/DOWN).
    - RETOUR_EQUILIBRE : `cassure_direction` est NULL en base (mean reversion) ;
      la direction est dérivée de la position de la force de la devise de base
      par rapport à l'équilibre neutre (50.0). Force > 50 (+deadband) = devise
      sur-achetée → réversion baissière ; force < 50 (-deadband) = sur-vendue →
      réversion haussière. Deadband autour de 50 pour ignorer le bruit.

    Retourne None (→ no_context, dégradation gracieuse R6) si la direction ne
    peut être établie proprement.
    """
    if regime_type in ("CASSURE", "EXTENSION"):
        return DIRECTION_FROM_CASSURE.get(cassure_direction)
    if regime_type == "RETOUR_EQUILIBRE":
        try:
            base_force = context_row[f"force_{base.lower()}"]
        except (KeyError, IndexError, TypeError):
            return None
        if base_force is None:
            return None
        base_force = float(base_force)
        if base_force > NEUTRAL_REFERENCE + REVERSION_DEADBAND:
            return "baissiere"
        if base_force < NEUTRAL_REFERENCE - REVERSION_DEADBAND:
            return "haussiere"
        return None
    return None


def _mtf_setup_label(regime_type: str | None) -> str:
    """Libellé descriptif du setup MTF selon le régime de contexte."""
    if regime_type == "CASSURE":
        return "sortie_zone_h4_croisement_m15"
    if regime_type == "RETOUR_EQUILIBRE":
        return "retour_equilibre_h4_confirmation_m15"
    return "extension_h4_recroisement_m15"


def _confluence_boost(trigger_confirmation: str | None, spread_abs: float) -> int:
    """Boost pondéré par la force de la confluence de confirmation (Gap 9).

    - croisement de forces (événement discret fort) → BOOST_ALIGNED (25, max) :
      conserve la valeur historique testée (non-régression).
    - alignement par spread → rampe linéaire de BOOST_ALIGNED_SPREAD_MIN (au
      seuil) à BOOST_ALIGNED (à 2× le seuil), bornée. Un alignement à peine au
      seuil vaut donc moins qu'un croisement franc.
    """
    if trigger_confirmation == "croisement":
        return BOOST_ALIGNED
    thr = float(SIGNAL_FORCES_FALLBACK_SPREAD_MIN)
    if thr <= 0:
        return BOOST_ALIGNED
    ratio = (spread_abs - thr) / thr  # 0 au seuil, 1 à 2× le seuil
    ratio = max(0.0, min(1.0, ratio))
    return int(round(
        BOOST_ALIGNED_SPREAD_MIN + (BOOST_ALIGNED - BOOST_ALIGNED_SPREAD_MIN) * ratio
    ))


def _generate_mtf_id(symbol: str, trigger_tf: str) -> str:
    compact_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"mtf_{compact_ts}_{symbol.lower()}_{trigger_tf.lower()}_{uuid.uuid4().hex[:6]}"

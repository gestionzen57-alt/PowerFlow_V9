"""v9_meta_strategy_shadow.py — Câblage shadow Phase E (Doctrine R25' strict).

**Pourquoi ce module existe** :
- `v9_meta_strategy_optimizer.py` recommande une stratégie parmi TP_SL / TRAILING /
  TP_PARTIAL / FAST_EXIT, mais n'est **PAS câblé runtime** (R25' strict motion CEO
  #32 : shadow d'abord, câblage = motion CEO distincte).
- Ce module expose `recommend_with_shadow()` qui :
  1. Appelle `StrategySelector.recommend()` (legacy, runtime actuel).
  2. Appelle `meta_strategy_optimizer.recommend()` (Phase E, non-runtime).
  3. Log les deux côte-à-côte dans la table `meta_strategy_shadow_log`
     (R2 additif strict : NE touche PAS principle_scores / paper_trades).
  4. Retourne la recommandation legacy (zéro impact runtime).
- Permet de mesurer edge uplift (legacy vs meta) sans risque de régression.

**Volet doctrinal** :
- R2 additif (clé `meta_strategy_*`, nouvelle table `meta_strategy_shadow_log`)
- R6 défensif (try/except global, fallback legacy garanti)
- R7 testable (DB in-memory, mock StrategySelector + mock meta)
- R18 code pur (zéro LLM, 100% stdlib)
- R25' strict (kill switch dédié, OFF par défaut, motion CEO requise pour activer)

**Volet performance attendu** :
- Cible : +5 pts WR / +0.5 PF mesurables sur sous-ensembles denses (≥10 trades / contexte)
- Comparaison bilatérale legacy vs meta après ≥500 shadow runs.

**Volet activation** :
- Kill switch `V9_META_STRATEGY_SHADOW_ENABLED` (défaut OFF, motion CEO pour activer).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ kill switch

META_STRATEGY_SHADOW_ENV = "V9_META_STRATEGY_SHADOW_ENABLED"


def meta_strategy_shadow_enabled() -> bool:
    """Kill switch — défaut OFF (R25' strict, motion CEO pour activer)."""
    val = os.environ.get(META_STRATEGY_SHADOW_ENV, "0")
    return val == "1"


# ------------------------------------------------------------------ dataclasses


@dataclass(frozen=True)
class ShadowComparison:
    """Comparaison legacy vs meta pour un appel unique.

    Attributs :
    - `symbol`, `timeframe`, `regime_type`, `phase`, `direction` : contexte
    - `legacy_strategy` : recommandé par StrategySelector (runtime actuel)
    - `legacy_confidence` : confiance legacy [0, 1]
    - `meta_strategy` : recommandé par meta_strategy_optimizer (Phase E)
    - `meta_confidence` : confiance meta [0, 1]
    - `meta_source` : source du choix meta (meta_optimizer / fallback / disabled)
    - `agreement` : True si legacy == meta
    - `shadow_id` : rowid dans meta_strategy_shadow_log (None si log skipped)
    """
    symbol: str
    timeframe: str
    regime_type: str
    phase: str
    direction: str
    legacy_strategy: str
    legacy_confidence: float
    meta_strategy: str
    meta_confidence: float
    meta_source: str
    agreement: bool
    shadow_id: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "regime_type": self.regime_type,
            "phase": self.phase,
            "direction": self.direction,
            "legacy_strategy": self.legacy_strategy,
            "legacy_confidence": self.legacy_confidence,
            "meta_strategy": self.meta_strategy,
            "meta_confidence": self.meta_confidence,
            "meta_source": self.meta_source,
            "agreement": self.agreement,
            "shadow_id": self.shadow_id,
        }


# ------------------------------------------------------------------ DB helpers


SHADOW_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS meta_strategy_shadow_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    regime_type TEXT NOT NULL,
    phase TEXT NOT NULL,
    direction TEXT NOT NULL,
    vol_atr_pips REAL,
    legacy_strategy TEXT NOT NULL,
    legacy_confidence REAL NOT NULL,
    legacy_tp REAL,
    legacy_sl REAL,
    meta_strategy TEXT NOT NULL,
    meta_confidence REAL NOT NULL,
    meta_tp REAL,
    meta_sl REAL,
    meta_source TEXT NOT NULL,
    agreement INTEGER NOT NULL,  -- 0/1
    rationale TEXT
);
CREATE INDEX IF NOT EXISTS idx_mssl_symbol_tf
    ON meta_strategy_shadow_log(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_mssl_created
    ON meta_strategy_shadow_log(created_at);
CREATE INDEX IF NOT EXISTS idx_mssl_agreement
    ON meta_strategy_shadow_log(agreement);
"""


def ensure_shadow_table(db_path: Path | str | None) -> bool:
    """Crée la table meta_strategy_shadow_log si absente. Retourne False si DB inaccessible.

    Si le fichier DB n'existe pas, on tente de le créer (R7 testable : tests tmp_path).
    Si db_path=None ou création impossible, retourne False.
    """
    if db_path is None:
        return False
    db_p = Path(db_path) if not isinstance(db_path, Path) else db_path
    try:
        # Crée parent dirs si nécessaire
        if db_p.parent and not db_p.parent.exists():
            db_p.parent.mkdir(parents=True, exist_ok=True)
        # sqlite3.connect crée le fichier si absent (et parents existent)
        conn = sqlite3.connect(str(db_p))
        try:
            conn.executescript(SHADOW_TABLE_DDL)
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.warning("meta_strategy_shadow: ensure_shadow_table failed: %s", e)
        return False


def _log_shadow(
    db_path: Path | str,
    *,
    symbol: str,
    timeframe: str,
    regime_type: str,
    phase: str,
    direction: str,
    vol_atr_pips: float | None,
    legacy_strategy: str,
    legacy_confidence: float,
    legacy_tp: float | None,
    legacy_sl: float | None,
    meta_strategy: str,
    meta_confidence: float,
    meta_tp: float | None,
    meta_sl: float | None,
    meta_source: str,
    agreement: bool,
    rationale: str | None,
) -> int | None:
    """Insère une ligne dans meta_strategy_shadow_log. Retourne rowid ou None si erreur."""
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute(
                """
                INSERT INTO meta_strategy_shadow_log (
                    created_at, symbol, timeframe, regime_type, phase, direction,
                    vol_atr_pips,
                    legacy_strategy, legacy_confidence, legacy_tp, legacy_sl,
                    meta_strategy, meta_confidence, meta_tp, meta_sl,
                    meta_source, agreement, rationale
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    time.time(),
                    symbol, timeframe, regime_type, phase, direction,
                    vol_atr_pips,
                    legacy_strategy, legacy_confidence, legacy_tp, legacy_sl,
                    meta_strategy, meta_confidence, meta_tp, meta_sl,
                    meta_source, 1 if agreement else 0, rationale,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()
    except Exception as e:
        logger.warning("meta_strategy_shadow: log insert failed: %s", e)
        return None


# ------------------------------------------------------------------ core


def recommend_with_shadow(
    *,
    symbol: str,
    timeframe: str,
    regime_type: str,
    phase: str,
    direction: str,
    vol_atr_pips: float | None = None,
    legacy_recommendation: Any,  # StrategyRecommendation (évite circular import)
    db_path: Path | str | None = None,
    meta_strategy_decision: Any | None = None,  # MetaStrategyDecision si déjà calculé
) -> tuple[Any, ShadowComparison | None]:
    """Compare legacy vs meta, log si kill switch ON, retourne (legacy, comparison_or_none).

    Args :
    - `legacy_recommendation` : résultat de `StrategySelector.recommend()`
      (objet duck-typed avec attributs `recommended_strategy`, `confidence`,
      `recommended_tp`, `recommended_sl`).
    - `meta_strategy_decision` : si None, le shadow appelle
      `meta_strategy_optimizer.recommend()` lui-même. Si déjà calculé par
      l'appelant, évite le double call.
    - `db_path` : chemin `v9_forces.db` pour log shadow (None = pas de log).

    Returns :
    - `(legacy_recommendation, comparison_or_none)` :
      - `comparison` = None si kill switch OFF, DB inaccessible, ou erreur.
      - `comparison` = ShadowComparison sinon, avec shadow_id du log.
    - Le legacy est **toujours retourné tel quel** (jamais écrasé par meta).
      R25' strict.
    """
    # Kill switch OFF ou DB inaccessible → retourner legacy sans rien faire
    if not meta_strategy_shadow_enabled():
        return legacy_recommendation, None
    if db_path is None or not Path(db_path).exists():
        return legacy_recommendation, None

    # Lecture défensive des attributs legacy (duck typing)
    legacy_strategy = getattr(legacy_recommendation, "recommended_strategy", "TP_SL")
    legacy_confidence = float(getattr(legacy_recommendation, "confidence", 0.0) or 0.0)
    legacy_tp = getattr(legacy_recommendation, "recommended_tp", None)
    legacy_sl = getattr(legacy_recommendation, "recommended_sl", None)

    # Calcul du meta si pas fourni
    if meta_strategy_decision is None:
        try:
            from core.v9.v9_meta_strategy_optimizer import (
                meta_strategy_optimizer_enabled,
                select_strategy as meta_recommend,
            )
            if not meta_strategy_optimizer_enabled():
                # Kill switch meta OFF → on log avec source=disabled_kill_switch
                meta_strategy_decision = None  # signalera via meta_source
            else:
                meta_strategy_decision = meta_recommend(
                    symbol=symbol,
                    timeframe=timeframe,
                    regime_type=regime_type,
                    phase=phase,
                    vol_atr_pips=vol_atr_pips,
                    direction=direction,
                    db_path=db_path,
                )
        except Exception as e:
            logger.warning("meta_strategy_shadow: meta recommend failed: %s", e)
            meta_strategy_decision = None

    # Lecture défensive meta
    if meta_strategy_decision is not None:
        meta_strategy = getattr(meta_strategy_decision, "chosen_strategy", "TP_SL")
        meta_confidence = float(getattr(meta_strategy_decision, "confidence", 0.0) or 0.0)
        meta_tp = getattr(meta_strategy_decision, "recommended_tp", None)
        meta_sl = getattr(meta_strategy_decision, "recommended_sl", None)
        meta_source = getattr(meta_strategy_decision, "source", "unknown")
        rationale = getattr(meta_strategy_decision, "rationale", None)
    else:
        meta_strategy = "TP_SL"
        meta_confidence = 0.0
        meta_tp = None
        meta_sl = None
        meta_source = "meta_kill_switch_off"
        rationale = "meta_strategy_optimizer_enabled()=False"

    agreement = (meta_strategy == legacy_strategy)

    # Ensure table (idempotent)
    if not ensure_shadow_table(db_path):
        return legacy_recommendation, None

    shadow_id = _log_shadow(
        db_path,
        symbol=symbol,
        timeframe=timeframe,
        regime_type=regime_type,
        phase=phase,
        direction=direction,
        vol_atr_pips=vol_atr_pips,
        legacy_strategy=legacy_strategy,
        legacy_confidence=legacy_confidence,
        legacy_tp=legacy_tp,
        legacy_sl=legacy_sl,
        meta_strategy=meta_strategy,
        meta_confidence=meta_confidence,
        meta_tp=meta_tp,
        meta_sl=meta_sl,
        meta_source=meta_source,
        agreement=agreement,
        rationale=rationale,
    )

    comparison = ShadowComparison(
        symbol=symbol,
        timeframe=timeframe,
        regime_type=regime_type,
        phase=phase,
        direction=direction,
        legacy_strategy=legacy_strategy,
        legacy_confidence=legacy_confidence,
        meta_strategy=meta_strategy,
        meta_confidence=meta_confidence,
        meta_source=meta_source,
        agreement=agreement,
        shadow_id=shadow_id,
    )

    return legacy_recommendation, comparison


# ------------------------------------------------------------------ rapport


def compute_edge_uplift(
    db_path: Path | str,
    *,
    since_ts: float | None = None,
) -> dict[str, Any]:
    """Calcule edge uplift legacy vs meta sur les shadow logs.

    Returns dict avec :
    - `n_shadows` : nombre de shadow logs
    - `agreement_rate` : % où legacy == meta
    - `meta_sources` : distribution des sources meta (meta_optimizer / fallback / etc.)
    - `strategy_distribution` : répartition par stratégie (legacy, meta)
    """
    db_p = Path(db_path)
    if not db_p.exists():
        return {"error": "db_not_found", "path": str(db_p)}

    try:
        conn = sqlite3.connect(str(db_p))
        try:
            conn.row_factory = sqlite3.Row
            where = ""
            params: tuple = ()
            if since_ts is not None:
                where = "WHERE created_at >= ?"
                params = (since_ts,)
            row = conn.execute(
                f"SELECT COUNT(*) AS n, AVG(agreement) AS agr FROM meta_strategy_shadow_log {where}",
                params,
            ).fetchone()
            n = row["n"] if row else 0
            agreement_rate = float(row["agr"]) if row and row["agr"] is not None else 0.0

            sources = {}
            for r in conn.execute(
                f"SELECT meta_source, COUNT(*) AS n FROM meta_strategy_shadow_log {where} "
                f"GROUP BY meta_source ORDER BY n DESC", params,
            ).fetchall():
                sources[r["meta_source"]] = int(r["n"])

            strat_legacy = {}
            for r in conn.execute(
                f"SELECT legacy_strategy, COUNT(*) AS n FROM meta_strategy_shadow_log {where} "
                f"GROUP BY legacy_strategy ORDER BY n DESC", params,
            ).fetchall():
                strat_legacy[r["legacy_strategy"]] = int(r["n"])

            strat_meta = {}
            for r in conn.execute(
                f"SELECT meta_strategy, COUNT(*) AS n FROM meta_strategy_shadow_log {where} "
                f"GROUP BY meta_strategy ORDER BY n DESC", params,
            ).fetchall():
                strat_meta[r["meta_strategy"]] = int(r["n"])

            return {
                "n_shadows": int(n),
                "agreement_rate": round(agreement_rate, 4),
                "meta_sources": sources,
                "strategy_legacy_distribution": strat_legacy,
                "strategy_meta_distribution": strat_meta,
            }
        finally:
            conn.close()
    except Exception as e:
        return {"error": "compute_failed", "detail": str(e)}
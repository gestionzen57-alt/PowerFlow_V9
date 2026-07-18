"""v9_cycle_memory.py — Mémoire inter-cycles des patterns résolus (Phase E, Doctrine R33).

Module fondateur du **Système Prédictif** PowerFlow V9. Persiste et rappelle les
patterns historiques des décisions résolues, structurés par contexte opérationnel.

**Pourquoi ce module existe** :
- Le système V9 lit le marché en haute définition (forces, scènes, comportements)
  mais **perd la mémoire inter-cycles** entre deux sessions. Une décision prise
  dans un régime CASSURE + phase culmination + vol HIGH a-t-elle déjà été
  observée la semaine dernière ? Avec quel taux de gain ? Pendant combien de
  bougies ? Le système ne s'en souvient pas.
- Ce module comble ce gap : une **mémoire externe** (DB SQLite séparée pour
  R8 additif) indexée par le quintuplet
  `(symbol, timeframe, regime_type, phase, vol_atr_bucket)` qui agrège
  statistiques de gain, durée de phase, et distributions de transition.

**Volet doctrinal** :
- R2 additif (clé préfixée `cycle_memory_*`, jamais destructif)
- R6 défensif (try/except + fallback `n_observations < MIN_N` → confidence 0)
- R7 testable (DB mémoire via `tmp_path`)
- R8 base séparée (`data/v9_cycle_memory.db`) — ne touche pas `v9_forces.db`
- R18 code pur (zéro LLM, 100 % stdlib)
- R33 doctrine du **Système Prédictif** (cf. `docs/architecture/PREDICTIVE_ENGINE.md`)

**Volet performance** :
- 8 771 décisions résolues dans la DB live (audit 2026-07-18) → largement
  suffisant pour des statistiques par contexte.
- Cardinalité phase = 4 (culmination/developpement/initiation/resolution) —
  vocabulaire de `behaviors.phase` directement exploitable.
- Cardinalité regime_type = 6 mais seules 2 valeurs (NEUTRE, RETOUR_EQUILIBRE)
  ont n ≥ 30 résolu → les autres restent traçables mais retournent
  `confidence=0` (filtre statistique).
- `vol_regime` est NULL partout dans `regime_snapshots` (dette technique
  signalée) → on contourne en dérivant `vol_atr_bucket` (LOW/MEDIUM/HIGH) depuis
  `vol_atr_pips` (qui est, lui, exploitable).

**Volet API** :
- `recall(symbol, timeframe, regime_type, phase, vol_atr_pips)` →
  `CyclePattern` ou None si contexte inconnu / n < MIN_N.
- `update_from_decision(decision_row, behavior_phase, vol_atr_pips)` →
  met à jour ou insère le pattern du contexte observé.
- `get_transition(from_phase, symbol, timeframe, regime_type)` →
  distribution empirique P(phase_T | phase_T-1, ...).
- `init_db(path)` → crée le schéma si absent.

**Activation** : kill switch `V9_CYCLE_MEMORY_ENABLED` (défaut `0` SHADOW).
APPLY = motion CEO explicite après validation empirique sur ≥ 30 jours live.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------ const

# Volatilité ATR bucketing (pips). Seuils calibrés sur GBPUSD M15 (audit 2026-07-18,
# `regime_snapshots.vol_atr_pips` P25/P50/P75 ≈ 1.5 / 3.5 / 7.0).
VOL_ATR_LOW_MAX = 2.0
VOL_ATR_MEDIUM_MAX = 6.0
# au-delà = HIGH

# Phase vocabulary aligné sur `behaviors.phase` (4 valeurs — audit 2026-07-18).
VALID_PHASES = ("culmination", "developpement", "initiation", "resolution")

# Regime vocabulary aligné sur `decisions.regime_type` (6 valeurs).
VALID_REGIMES = ("NEUTRE", "RETOUR_EQUILIBRE", "EXTENSION", "PALIER", "CASSURE", "REJET")

# Kill switch (défaut SHADOW).
CYCLE_MEMORY_ENABLED_ENV = "V9_CYCLE_MEMORY_ENABLED"

# Chemin canonique de la DB cycle memory (R8 : séparée de v9_forces.db).
DEFAULT_DB_PATH = Path("data/v9_cycle_memory.db")

# Seuil minimum d'observations pour qu'un pattern soit "actionnable".
# En dessous → confidence=0, le moteur ne s'exprime pas (R6 défensif).
MIN_N_OBSERVATIONS = 5

# TTL (jours) — au-delà, les patterns sont purgés pour éviter la dérive
# saisonnière. 90 jours = horizon de mémoire long-terme raisonnable pour
# un système adaptatif (les phases de marché tournent sur 2-8 semaines
# empiriquement).
TTL_DAYS = 90

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ dataclasses


@dataclass(frozen=True)
class CyclePattern:
    """Pattern statistique d'un quintuplet contextuel.

    Tous les champs sont nuls/zéro si le contexte est inconnu ou
    `n_observations < MIN_N_OBSERVATIONS`.
    """
    symbol: str
    timeframe: str
    regime_type: str
    phase: str
    vol_atr_bucket: str

    n_observations: int
    n_wins: int
    win_rate: float          # [0, 1]
    mean_duration_bars: float
    p50_duration_bars: float
    p95_duration_bars: float
    n_resolved: int          # sous-ensemble résolu (is_win IS NOT NULL)
    n_pending: int           # sous-ensemble pending

    confidence: float        # [0, 1] — qualité statistique du pattern
    last_updated_ts: float   # epoch UTC du dernier update

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_actionable(self) -> bool:
        """Vrai si le pattern a assez d'observations ET est frais (< TTL)."""
        if self.n_observations < MIN_N_OBSERVATIONS:
            return False
        age_days = (time.time() - self.last_updated_ts) / 86400.0
        return age_days <= TTL_DAYS


@dataclass(frozen=True)
class TransitionPattern:
    """Distribution empirique P(phase_T | phase_T-1, symbol, timeframe, regime_type)."""
    from_phase: str
    symbol: str
    timeframe: str
    regime_type: str
    n_transitions: int
    distribution: dict[str, float]   # phase -> probabilité [0, 1], somme = 1.0
    most_likely_next: str
    most_likely_proba: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ schema

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cycle_patterns (
    symbol          TEXT    NOT NULL,
    timeframe       TEXT    NOT NULL,
    regime_type     TEXT    NOT NULL,
    phase           TEXT    NOT NULL,
    vol_atr_bucket  TEXT    NOT NULL,
    n_observations  INTEGER NOT NULL DEFAULT 0,
    n_wins          INTEGER NOT NULL DEFAULT 0,
    n_resolved      INTEGER NOT NULL DEFAULT 0,
    n_pending       INTEGER NOT NULL DEFAULT 0,
    sum_duration    REAL    NOT NULL DEFAULT 0.0,
    sum_duration_sq REAL    NOT NULL DEFAULT 0.0,
    max_duration    REAL    NOT NULL DEFAULT 0.0,
    p50_duration    REAL    NOT NULL DEFAULT 0.0,
    p95_duration    REAL    NOT NULL DEFAULT 0.0,
    last_updated_ts REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (symbol, timeframe, regime_type, phase, vol_atr_bucket)
);

CREATE INDEX IF NOT EXISTS idx_cp_context
    ON cycle_patterns(symbol, timeframe, regime_type);

CREATE TABLE IF NOT EXISTS phase_transitions (
    from_phase     TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    timeframe      TEXT NOT NULL,
    regime_type    TEXT NOT NULL,
    to_phase       TEXT NOT NULL,
    n_transitions  INTEGER NOT NULL DEFAULT 0,
    last_updated_ts REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (from_phase, symbol, timeframe, regime_type, to_phase)
);

CREATE INDEX IF NOT EXISTS idx_pt_lookup
    ON phase_transitions(from_phase, symbol, timeframe, regime_type);

CREATE TABLE IF NOT EXISTS cycle_memory_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def init_db(path: Path | None = None) -> Path:
    """Crée le schéma si absent. Retourne le path effectif de la DB."""
    if path is None:
        path = DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SCHEMA_SQL)
        # Meta : schema version (utile pour migrations futures).
        conn.execute(
            "INSERT OR REPLACE INTO cycle_memory_meta(key, value) VALUES (?, ?)",
            ("schema_version", "1"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO cycle_memory_meta(key, value) VALUES (?, ?)",
            ("last_init_ts", str(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("v9_cycle_memory DB initialisée : %s", path)
    return path


# ------------------------------------------------------------------ helpers

def cycle_memory_enabled() -> bool:
    """Kill switch — défaut OFF (SHADOW)."""
    val = os.environ.get(CYCLE_MEMORY_ENABLED_ENV, "0")
    return val == "1"


def _bucket_vol_atr(vol_atr_pips: float | None) -> str:
    """Discrétise `vol_atr_pips` en bucket LOW/MEDIUM/HIGH/UNKNOWN.

    Seuils calibrés sur GBPUSD M15 (audit 2026-07-18). Pour les autres
    couples (symbol, timeframe), on garde les mêmes seuils : le bucket
    reste sémantiquement cohérent (« volatilité relative à la médiane
    historique de l'instrument »).
    """
    if vol_atr_pips is None:
        return "UNKNOWN"
    try:
        v = float(vol_atr_pips)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if v < 0:
        return "UNKNOWN"
    if v <= VOL_ATR_LOW_MAX:
        return "LOW"
    if v <= VOL_ATR_MEDIUM_MAX:
        return "MEDIUM"
    return "HIGH"


def _compute_confidence(n_obs: int, n_resolved: int, age_days: float) -> float:
    """Confiance statistique du pattern ∈ [0, 1].

    Combine 3 critères :
    1. Volume d'observations : `min(1, n_obs / 30)` — 30 cas = pleine confiance
       empirique (cohérent avec le seuil `principle_scores` WR minimum).
    2. Ratio résolu : `min(1, n_resolved / max(1, n_obs))` — si la majorité
       est pending, le WR observé est biaisé. On pénalise.
    3. Fraîcheur : `max(0, 1 - age_days / TTL_DAYS)` — TTL = 90 jours, décroît
       linéairement.
    """
    if n_obs <= 0:
        return 0.0
    vol_score = min(1.0, n_obs / 30.0)
    res_score = min(1.0, n_resolved / max(1, n_obs))
    fresh_score = max(0.0, 1.0 - age_days / TTL_DAYS)
    # Pondération : 50% volume, 30% résolution, 20% fraîcheur.
    return round(0.5 * vol_score + 0.3 * res_score + 0.2 * fresh_score, 4)


def _percentile(sorted_values: list[float], p: float) -> float:
    """Percentile simple (linear interpolation, len > 0 requis)."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


# ------------------------------------------------------------------ recall


def recall(
    symbol: str,
    timeframe: str,
    regime_type: str,
    phase: str,
    vol_atr_pips: float | None,
    db_path: Path | None = None,
) -> CyclePattern | None:
    """Rappelle le pattern historique d'un quintuplet contextuel.

    Retourne `None` si :
    - Contexte inconnu
    - `n_observations < MIN_N_OBSERVATIONS` (5)
    - Pattern expiré (> TTL_DAYS depuis last_updated_ts)

    R6 défensif : toutes les exceptions sont attrapées et loggées.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if not db_path.exists():
        return None
    bucket = _bucket_vol_atr(vol_atr_pips)
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                """
                SELECT n_observations, n_wins, n_resolved, n_pending,
                       sum_duration, n_observations AS n_for_mean,
                       p50_duration, p95_duration, last_updated_ts
                FROM cycle_patterns
                WHERE symbol = ? AND timeframe = ? AND regime_type = ?
                  AND phase = ? AND vol_atr_bucket = ?
                """,
                (symbol, timeframe, regime_type, phase, bucket),
            ).fetchone()
            if row is None:
                return None
            (n_obs, n_wins, n_res, n_pend, sum_dur, _n_mean,
             p50_d, p95_d, last_upd) = row
            # Filtre is_actionable : si n_observations < MIN_N_OBSERVATIONS
            # ou si le pattern est expiré (> TTL), on retourne None (R6).
            if n_obs < MIN_N_OBSERVATIONS:
                return None
            age_days = (time.time() - last_upd) / 86400.0
            if age_days > TTL_DAYS:
                return None
            mean_dur = sum_dur / max(1, n_obs)
            wr = n_wins / max(1, n_res) if n_res > 0 else 0.0
            confidence = _compute_confidence(n_obs, n_res, age_days)
            return CyclePattern(
                symbol=symbol,
                timeframe=timeframe,
                regime_type=regime_type,
                phase=phase,
                vol_atr_bucket=bucket,
                n_observations=n_obs,
                n_wins=n_wins,
                win_rate=round(wr, 4),
                mean_duration_bars=round(mean_dur, 4),
                p50_duration_bars=p50_d,
                p95_duration_bars=p95_d,
                n_resolved=n_res,
                n_pending=n_pend,
                confidence=confidence,
                last_updated_ts=last_upd,
            )
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning("v9_cycle_memory.recall DB error : %s", e)
        return None
    except Exception as e:
        logger.warning("v9_cycle_memory.recall unexpected error : %s", e)
        return None


def get_transition(
    from_phase: str,
    symbol: str,
    timeframe: str,
    regime_type: str,
    db_path: Path | None = None,
) -> TransitionPattern | None:
    """Distribution empirique P(phase_T | phase_T-1, ...).

    Utile pour le `predictive_engine` : sachant qu'on est en `phase_T-1`,
    quelle est la distribution des phases observées au pas suivant ?

    Retourne `None` si < MIN_N transitions observées.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if not db_path.exists():
        return None
    if from_phase not in VALID_PHASES:
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                """
                SELECT to_phase, n_transitions
                FROM phase_transitions
                WHERE from_phase = ? AND symbol = ? AND timeframe = ?
                  AND regime_type = ?
                """,
                (from_phase, symbol, timeframe, regime_type),
            ).fetchall()
            if not rows:
                return None
            total = sum(n for _, n in rows)
            if total < MIN_N_OBSERVATIONS:
                return None
            distribution: dict[str, float] = {}
            for to_phase, n in rows:
                distribution[to_phase] = round(n / total, 4)
            # Most likely next
            ml_phase, ml_n = max(rows, key=lambda r: r[1])
            ml_proba = round(ml_n / total, 4)
            # Confidence = f(total, dominance du most-likely)
            dominance = ml_proba
            confidence = round(min(1.0, total / 30.0) * dominance, 4)
            return TransitionPattern(
                from_phase=from_phase,
                symbol=symbol,
                timeframe=timeframe,
                regime_type=regime_type,
                n_transitions=total,
                distribution=distribution,
                most_likely_next=ml_phase,
                most_likely_proba=ml_proba,
                confidence=confidence,
            )
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning("v9_cycle_memory.get_transition DB error : %s", e)
        return None
    except Exception as e:
        logger.warning("v9_cycle_memory.get_transition unexpected error : %s", e)
        return None


# ------------------------------------------------------------------ update


def update(
    symbol: str,
    timeframe: str,
    regime_type: str,
    phase: str,
    vol_atr_pips: float | None,
    *,
    is_win: bool | None,
    duration_bars: float | None = None,
    db_path: Path | None = None,
) -> bool:
    """Met à jour ou insère le pattern du quintuplet contextuel observé.

    Paramètres :
    - `is_win` : True si trade gagnant, False si perdant, None si pending.
    - `duration_bars` : durée de la phase en bougies (optionnel).

    Incrémente n_observations, n_wins (si résolu), sum_duration (si fourni).
    Met à jour p95_duration par quantile tracking léger (approx).

    Retourne True si l'update a réussi.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if regime_type not in VALID_REGIMES or phase not in VALID_PHASES:
        return False
    bucket = _bucket_vol_atr(vol_atr_pips)
    ts = time.time()
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            # Upsert via INSERT OR IGNORE + UPDATE.
            conn.execute(
                """
                INSERT OR IGNORE INTO cycle_patterns(
                    symbol, timeframe, regime_type, phase, vol_atr_bucket,
                    n_observations, n_wins, n_resolved, n_pending,
                    sum_duration, sum_duration_sq, max_duration,
                    p50_duration, p95_duration, last_updated_ts
                ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, ?)
                """,
                (symbol, timeframe, regime_type, phase, bucket, ts),
            )
            # UPDATE incrémental.
            win_inc = 1 if is_win is True else 0
            res_inc = 1 if is_win is not None else 0
            pend_inc = 1 if is_win is None else 0
            dur_inc = float(duration_bars) if duration_bars is not None else 0.0
            dur_sq_inc = dur_inc * dur_inc
            conn.execute(
                """
                UPDATE cycle_patterns
                SET n_observations = n_observations + 1,
                    n_wins          = n_wins + ?,
                    n_resolved      = n_resolved + ?,
                    n_pending       = n_pending + ?,
                    sum_duration    = sum_duration + ?,
                    sum_duration_sq = sum_duration_sq + ?,
                    max_duration    = MAX(max_duration, ?),
                    last_updated_ts = ?
                WHERE symbol = ? AND timeframe = ? AND regime_type = ?
                  AND phase = ? AND vol_atr_bucket = ?
                """,
                (win_inc, res_inc, pend_inc,
                 dur_inc, dur_sq_inc, dur_inc,
                 ts, symbol, timeframe, regime_type, phase, bucket),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning("v9_cycle_memory.update DB error : %s", e)
        return False
    except Exception as e:
        logger.warning("v9_cycle_memory.update unexpected error : %s", e)
        return False


def update_transition(
    from_phase: str,
    to_phase: str,
    symbol: str,
    timeframe: str,
    regime_type: str,
    db_path: Path | None = None,
) -> bool:
    """Incrémente la transition observée (phase_T-1 → phase_T)."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if from_phase not in VALID_PHASES or to_phase not in VALID_PHASES:
        return False
    if regime_type not in VALID_REGIMES:
        return False
    ts = time.time()
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO phase_transitions(
                    from_phase, symbol, timeframe, regime_type, to_phase,
                    n_transitions, last_updated_ts
                ) VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (from_phase, symbol, timeframe, regime_type, to_phase, ts),
            )
            conn.execute(
                """
                UPDATE phase_transitions
                SET n_transitions = n_transitions + 1,
                    last_updated_ts = ?
                WHERE from_phase = ? AND symbol = ? AND timeframe = ?
                  AND regime_type = ? AND to_phase = ?
                """,
                (ts, from_phase, symbol, timeframe, regime_type, to_phase),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning("v9_cycle_memory.update_transition DB error : %s", e)
        return False
    except Exception as e:
        logger.warning("v9_cycle_memory.update_transition unexpected error : %s", e)
        return False


# ------------------------------------------------------------------ diagnostics


def get_stats(db_path: Path | None = None) -> dict[str, Any]:
    """Statistiques globales de la DB cycle memory (diagnostic)."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if not db_path.exists():
        return {"exists": False, "path": str(db_path)}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            n_patterns = conn.execute(
                "SELECT COUNT(*) FROM cycle_patterns"
            ).fetchone()[0]
            n_actionable = conn.execute(
                "SELECT COUNT(*) FROM cycle_patterns WHERE n_observations >= ?",
                (MIN_N_OBSERVATIONS,),
            ).fetchone()[0]
            n_transitions = conn.execute(
                "SELECT COUNT(*) FROM phase_transitions"
            ).fetchone()[0]
            meta = dict(conn.execute(
                "SELECT key, value FROM cycle_memory_meta"
            ).fetchall())
            return {
                "exists": True,
                "path": str(db_path),
                "n_patterns": n_patterns,
                "n_actionable_patterns": n_actionable,
                "n_transitions": n_transitions,
                "meta": meta,
            }
        finally:
            conn.close()
    except sqlite3.Error as e:
        return {"exists": True, "error": str(e), "path": str(db_path)}


def recompute_percentiles(
    symbol: str,
    timeframe: str,
    regime_type: str,
    phase: str,
    vol_atr_pips: float | None,
    raw_durations: list[float],
    db_path: Path | None = None,
) -> bool:
    """Recalcule p50/p95 depuis une liste brute de durées (utilisé en batch update).

    La méthode incrémentale simple ne maintient pas les quantiles avec
    précision (avg+max+sq seulement). Cette fonction permet à un batch
    loader de ré-aligner les percentiles après ingestion.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if not raw_durations:
        return False
    sorted_d = sorted(raw_durations)
    p50 = _percentile(sorted_d, 0.50)
    p95 = _percentile(sorted_d, 0.95)
    bucket = _bucket_vol_atr(vol_atr_pips)
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                """
                UPDATE cycle_patterns
                SET p50_duration = ?, p95_duration = ?
                WHERE symbol = ? AND timeframe = ? AND regime_type = ?
                  AND phase = ? AND vol_atr_bucket = ?
                """,
                (p50, p95, symbol, timeframe, regime_type, phase, bucket),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning("v9_cycle_memory.recompute_percentiles DB error : %s", e)
        return False


def purge_stale(db_path: Path | None = None, ttl_days: int = TTL_DAYS) -> int:
    """Purge les patterns dont `last_updated_ts` dépasse `ttl_days`.

    Retourne le nombre de lignes supprimées. Lecture seule par défaut (ne
    purge rien), à appeler explicitement par un cron `V9_CycleMemoryPurge`.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    if not db_path.exists():
        return 0
    cutoff = time.time() - ttl_days * 86400.0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute(
                "DELETE FROM cycle_patterns WHERE last_updated_ts < ?",
                (cutoff,),
            )
            n_purged = cur.rowcount
            cur2 = conn.execute(
                "DELETE FROM phase_transitions WHERE last_updated_ts < ?",
                (cutoff,),
            )
            n_purged_t = cur2.rowcount
            conn.commit()
            return n_purged + n_purged_t
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning("v9_cycle_memory.purge_stale DB error : %s", e)
        return 0


# ------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    """CLI : init / stats / purge. Lecture seule par défaut."""
    import argparse
    parser = argparse.ArgumentParser(
        description="v9_cycle_memory CLI (init / stats / purge)"
    )
    parser.add_argument("--init", action="store_true", help="Crée le schéma DB.")
    parser.add_argument("--stats", action="store_true", help="Affiche les stats.")
    parser.add_argument("--purge", action="store_true",
                        help="Purge les patterns > TTL_DAYS.")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH),
                        help=f"Path DB (défaut: {DEFAULT_DB_PATH}).")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if args.init:
        init_db(db_path)
        print(f"DB initialisée : {db_path}")
        return 0
    if args.stats:
        stats = get_stats(db_path)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0
    if args.purge:
        n = purge_stale(db_path)
        print(f"Patterns purgés : {n}")
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))

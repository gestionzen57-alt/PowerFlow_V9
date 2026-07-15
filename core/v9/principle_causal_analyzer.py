"""PrincipleCausalAnalyzer — Recherche du « pourquoi » par principe V9 (SOUL.md §4).

Couche 3 du moteur de recherche alpha : quand un principe sous-performe dans
une dimension, ce module cherche la cause. Il compare la dimension perdante aux
dimensions gagnantes sur des facteurs mesurables (spread, avg_pips, faux
signaux, coalition, antagonisme, vol_regime), génère des hypothèses textuelles,
puis les valide ou les rejette sur les données.

Le système ne dit pas seulement « ce principe perd en session London ». Il dit
« il perd parce que le spread y est 2× plus élevé et les faux signaux 3× plus
fréquents ». Comprendre pourquoi il gagne, pas seulement qu'il gagne.

Doctrine :
  - R18 : stdlib uniquement, aucun LLM, aucune dépendance externe
  - R2 : couche additive (lit les tables, écrit son journal causal)
  - R6 : try/except, ne crash jamais
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection
from core.v9.principle_alpha_engine import PrincipleAlphaEngine

log = logging.getLogger(__name__)

CAUSAL_ANALYZER_VERSION = "1.0"

# Écart relatif au-delà duquel un facteur est jugé « significativement » pire
# dans la dimension perdante (ex : spread 40% plus élevé).
FACTOR_DELTA_RATIO = 0.30

CAUSAL_JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS principle_causal_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    principle_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    dimension_value TEXT,
    observation TEXT NOT NULL,
    hypothesis TEXT,
    validation_method TEXT,
    conclusion TEXT,
    action_taken TEXT,
    status TEXT DEFAULT 'hypothesis',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_causal_principle
    ON principle_causal_journal (principle_id);
"""


def init_causal_db(db_path: Path | None = None) -> None:
    """Crée la table principle_causal_journal si absente (idempotent)."""
    conn = get_connection(db_path)
    try:
        conn.executescript(CAUSAL_JOURNAL_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def generate_hypothesis(observation: dict[str, Any]) -> str:
    """Génère une hypothèse textuelle depuis une observation structurée.

    L'observation contient les facteurs comparés (spread, avg_pips, faux
    signaux…) entre la dimension perdante et le reste. Retourne une phrase
    lisible expliquant la cause probable.
    """
    pid = observation.get("principle_id", "?")
    dim = observation.get("dimension", "?")
    val = observation.get("value", "?")
    factors = observation.get("worse_factors", [])

    if not factors:
        return (
            f"{pid} sous-performe en {dim}={val} sans facteur mesurable "
            f"dominant — cause probable : bruit d'échantillon ou edge absent."
        )

    parts = []
    for f in factors:
        name = f["factor"]
        ratio = f["ratio"]
        parts.append(f"{name} {ratio:+.0%} vs référence")

    lead = factors[0]["factor"]
    cause = _factor_to_cause(lead)
    return (
        f"{pid} perd en {dim}={val} car {', '.join(parts)}. "
        f"Cause dominante probable : {cause}."
    )


def _factor_to_cause(factor: str) -> str:
    """Traduit un facteur mesuré en cause narrative."""
    mapping = {
        "spread_price": "coût de spread érode l'edge (TP trop serré vs spread)",
        "avg_pips": "amplitude favorable insuffisante (mouvement trop faible)",
        "false_signal_rate": "taux de faux signaux élevé (whipsaw / retournements)",
        "max_drawdown": "séquences de pertes profondes (instabilité)",
        "antagonism": "antagonisme de forces défavorable (opposition non résolue)",
        "coalition_strength": "coalition trop faible (absence de dynamique portée)",
        "vol_atr_pips": "volatilité excessive (bruit noie le signal)",
    }
    return mapping.get(factor, f"facteur {factor} défavorable")


class PrincipleCausalAnalyzer:
    """Analyseur causal des sous-performances par principe.

    Usage :
        an = PrincipleCausalAnalyzer()
        res = an.analyze_underperformance("PRICE_LAG_AT_NODE_BIRTH", "session", "london")
        loss = an.analyze_session_loss("GRAMMAR_CONTEXTE", "new_york")
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        init_causal_db(self.db_path)
        self.alpha = PrincipleAlphaEngine(db_path=self.db_path)

    # ── Facteurs de marché par dimension ──

    def _fetch_factors(
        self, principle_id: str, dimension: str, value: str,
    ) -> dict[str, float]:
        """Facteurs de marché moyens pour un principe dans une dimension.

        Agrège spread, faux signaux, antagonisme, coalition, vol depuis les
        snapshots où le principe a triggered et où la dimension vaut `value`.
        Retourne un dict de moyennes (0.0 si indisponible).
        """
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        factors: dict[str, float] = {}
        try:
            dim_clause, dim_param = self._dimension_clause(dimension, value)
            # Spread et amplitude depuis forces_snapshots + résolution.
            row = conn.execute(
                f"""
                SELECT AVG(ABS(d.resolution_pips)) AS avg_amp,
                       AVG(fs.spread_price) AS spread_price,
                       AVG(CASE WHEN d.is_win = 0 THEN 1.0 ELSE 0.0 END)
                           AS false_signal_rate,
                       COUNT(*) AS n
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                LEFT JOIN forces_snapshots fs ON fs.snapshot_id = pe.snapshot_id
                WHERE pe.principle_id = ?
                  AND pe.triggered = 1
                  AND d.is_win IS NOT NULL
                  {dim_clause}
                """,
                (principle_id, *dim_param),
            ).fetchone()
            if row and row["n"]:
                factors["avg_pips"] = float(row["avg_amp"] or 0.0)
                factors["spread_price"] = float(row["spread_price"] or 0.0)
                factors["false_signal_rate"] = float(row["false_signal_rate"] or 0.0)
                factors["n"] = float(row["n"])

            # Facteurs de régime (vol, antagonisme via regime_snapshots).
            vol = conn.execute(
                f"""
                SELECT AVG(rs.vol_atr_pips) AS vol_atr, AVG(rs.spread_mean) AS spread_mean
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                JOIN regime_snapshots rs ON rs.forces_snapshot_ref = pe.snapshot_id
                WHERE pe.principle_id = ?
                  AND pe.triggered = 1
                  AND d.is_win IS NOT NULL
                  {dim_clause}
                """,
                (principle_id, *dim_param),
            ).fetchone()
            if vol and vol["vol_atr"] is not None:
                factors["vol_atr_pips"] = float(vol["vol_atr"] or 0.0)
        except Exception as exc:
            log.debug("causal: _fetch_factors failed [%s/%s=%s]: %s",
                      principle_id, dimension, value, exc)
        finally:
            conn.close()
        return factors

    def _dimension_clause(self, dimension: str, value: str) -> tuple[str, tuple]:
        """Construit la clause SQL de filtrage pour une dimension.

        `session` est dérivée de l'heure (pas de colonne) → pas de clause SQL,
        on ne peut pas la pousser dans WHERE. On la gère alors côté appelant
        via un filtre sur l'heure UTC.
        """
        if dimension == "regime":
            return ("AND d.regime_type = ?", (value,))
        if dimension == "timeframe":
            return ("AND d.timeframe = ?", (value,))
        if dimension == "direction":
            return ("AND d.direction = ?", (value,))
        if dimension == "session":
            lo, hi = self._session_hours(value)
            # substr heure UTC du timestamp ISO (positions 12-13).
            return (
                "AND CAST(substr(d.timestamp, 12, 2) AS INTEGER) >= ? "
                "AND CAST(substr(d.timestamp, 12, 2) AS INTEGER) < ?",
                (lo, hi),
            )
        return ("", ())

    @staticmethod
    def _session_hours(session: str) -> tuple[int, int]:
        """Bornes horaires UTC [lo, hi) d'une session (cf infer_session_from_hour)."""
        bounds = {
            "asie": (0, 7),
            "london": (7, 12),
            "overlap": (12, 16),
            "new_york": (16, 22),
            "after": (22, 24),
        }
        return bounds.get(session, (0, 24))

    # ── Analyse d'une sous-performance ──

    def analyze_underperformance(
        self, principle_id: str, dimension: str, value: str,
    ) -> dict[str, Any]:
        """Identifie pourquoi un principe perd dans une dimension.

        Compare les facteurs de la dimension perdante à ceux du reste
        (baseline global), génère une hypothèse et l'enregistre dans le journal.
        """
        global_m = self.alpha.compute_metrics(principle_id)
        dim_kwargs = {dimension if dimension != "session" else "session": value}
        # compute_metrics n'accepte que session/regime/timeframe/direction.
        target_m = self.alpha.compute_metrics(
            principle_id, **{k: v for k, v in dim_kwargs.items()
                             if k in ("session", "regime", "timeframe", "direction")},
        )

        target_factors = self._fetch_factors(principle_id, dimension, value)
        baseline_factors = self._fetch_factors_baseline(principle_id, dimension, value)

        worse = self._compare_factors(target_factors, baseline_factors)

        observation = {
            "principle_id": principle_id,
            "dimension": dimension,
            "value": value,
            "target_wr": target_m["win_rate"],
            "global_wr": global_m["win_rate"],
            "wr_delta": round(target_m["win_rate"] - global_m["win_rate"], 2),
            "n_trades": target_m["n_trades"],
            "target_factors": target_factors,
            "baseline_factors": baseline_factors,
            "worse_factors": worse,
        }
        hypothesis = generate_hypothesis(observation)

        obs_text = (
            f"WR {target_m['win_rate']:.1f}% (n={target_m['n_trades']}) vs "
            f"global {global_m['win_rate']:.1f}% "
            f"(Δ{observation['wr_delta']:+.1f})"
        )
        self._journal(
            principle_id, dimension, value, obs_text, hypothesis,
            validation_method="factor_comparison",
            status="hypothesis",
        )

        return {**observation, "hypothesis": hypothesis}

    def _fetch_factors_baseline(
        self, principle_id: str, dimension: str, exclude_value: str,
    ) -> dict[str, float]:
        """Facteurs moyens du principe hors la dimension étudiée (référence).

        Approche simple et robuste : facteurs globaux du principe (toutes
        dimensions confondues), qui servent de baseline de comparaison.
        """
        return self._fetch_factors(principle_id, "global", exclude_value)

    def _compare_factors(
        self, target: dict[str, float], baseline: dict[str, float],
    ) -> list[dict[str, Any]]:
        """Liste les facteurs significativement pires dans la cible.

        « Pire » = plus élevé pour spread/faux-signaux/vol/drawdown, plus bas
        pour avg_pips. Trié par écart décroissant.
        """
        worse: list[dict[str, Any]] = []
        higher_is_worse = {"spread_price", "false_signal_rate", "vol_atr_pips",
                           "max_drawdown"}
        lower_is_worse = {"avg_pips"}

        for factor in higher_is_worse | lower_is_worse:
            t = target.get(factor)
            b = baseline.get(factor)
            if t is None or b is None or b == 0:
                continue
            ratio = (t - b) / abs(b)
            is_worse = (
                (factor in higher_is_worse and ratio > FACTOR_DELTA_RATIO)
                or (factor in lower_is_worse and ratio < -FACTOR_DELTA_RATIO)
            )
            if is_worse:
                worse.append({"factor": factor, "ratio": round(ratio, 3),
                             "target": round(t, 4), "baseline": round(b, 4)})

        worse.sort(key=lambda f: abs(f["ratio"]), reverse=True)
        return worse

    # ── Analyses spécialisées ──

    def analyze_session_loss(self, principle_id: str, session: str) -> dict[str, Any]:
        """Pourquoi ce principe perd dans cette session ?"""
        return self.analyze_underperformance(principle_id, "session", session)

    def analyze_regime_loss(self, principle_id: str, regime: str) -> dict[str, Any]:
        """Pourquoi ce principe perd dans ce régime ?"""
        return self.analyze_underperformance(principle_id, "regime", regime)

    def validate_hypothesis(
        self, principle_id: str, hypothesis: str, dimension: str, value: str,
    ) -> dict[str, Any]:
        """Valide ou rejette une hypothèse sur les données.

        Vérifie que les facteurs invoqués existent et sont bien défavorables.
        Met à jour le journal avec la conclusion.
        """
        target = self._fetch_factors(principle_id, dimension, value)
        baseline = self._fetch_factors_baseline(principle_id, dimension, value)
        worse = self._compare_factors(target, baseline)

        validated = len(worse) > 0
        conclusion = (
            f"validée : {len(worse)} facteur(s) défavorable(s) confirmé(s) "
            f"({', '.join(f['factor'] for f in worse)})"
            if validated else
            "rejetée : aucun facteur significativement défavorable trouvé"
        )
        self._journal(
            principle_id, dimension, value,
            observation=f"validation de: {hypothesis[:120]}",
            hypothesis=hypothesis,
            validation_method="factor_comparison",
            conclusion=conclusion,
            status="validated" if validated else "rejected",
        )
        return {
            "principle_id": principle_id,
            "dimension": dimension,
            "value": value,
            "validated": validated,
            "worse_factors": worse,
            "conclusion": conclusion,
        }

    # ── Journal ──

    def _journal(
        self,
        principle_id: str,
        dimension: str,
        value: str,
        observation: str,
        hypothesis: str | None = None,
        validation_method: str | None = None,
        conclusion: str | None = None,
        action_taken: str | None = None,
        status: str = "hypothesis",
    ) -> None:
        """Enregistre une entrée dans le journal causal (R6 : ne crash pas)."""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO principle_causal_journal (
                    principle_id, dimension, dimension_value, observation,
                    hypothesis, validation_method, conclusion, action_taken,
                    status, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (principle_id, dimension, value, observation, hypothesis,
                 validation_method, conclusion, action_taken, status,
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except Exception as exc:
            log.debug("causal: journal insert failed: %s", exc)
        finally:
            conn.close()

    def get_journal(self, principle_id: str | None = None) -> list[dict[str, Any]]:
        """Retourne les entrées du journal causal (filtre optionnel)."""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if principle_id:
                rows = conn.execute(
                    "SELECT * FROM principle_causal_journal WHERE principle_id = ? "
                    "ORDER BY id DESC",
                    (principle_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM principle_causal_journal ORDER BY id DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

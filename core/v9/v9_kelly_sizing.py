"""v9_kelly_sizing.py — Câblage du multiplicateur Kelly bayésien (Axe 1.2 / J2).

L'Axe 1.1 (J1) a livré `bayesian_calibrator.py` : Beta(α,β) postérieur du WR
par contexte + `kelly_fraction()` → multiplicateur de taille borné. Ce module
**câble** ce multiplicateur dans la chaîne de sizing du `trade_engine`, sans
remplacer le `DynamicRiskManager` ni le sizing statique existant.

Pourquoi Kelly bayésien plutôt que la confiance déclarée ? Le Brier score 7j
= 0.4467 (mesuré 2026-07-21) : la confiance déclarée est **anti-calibrée**
(gap jusqu'à −0.53 sur le décile 0.9-1.0). Sizer sur cette confiance est
anti-Kelly — on amplifie le risque là où l'edge n'existe pas. Le posterior
Beta, lui, agrège les WIN/LOSS **réels** par contexte : c'est la seule base
de sizing probabiliste honnête dont dispose le système.

Composition **multiplicative** (jamais un remplacement) :

    final_size = base_size × dynamic_risk_multiplier × kelly_multiplier

Le multiplicateur Kelly reste dans [floor=0.3, cap=2.0]. Il vaut 1.0 (neutre)
si : kill switch OFF, n<MIN_N (20), edge non confirmé (P(WR>0.5)<0.6), pas
d'edge positif, ou erreur (fail-safe R6). Lecture seule DB (mode=ro via le
BayesianCalibrator) — aucune écriture, aucune migration.

Doctrine : R2 (additif), R6 (défensif — ne lève jamais côté sizing), R18
(code pur, zéro LLM), R25' (OFF par défaut, kill switch V9_KELLY_FRACTIONAL_ENABLED).
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from core.v9.bayesian_calibrator import BayesianCalibrator
from core.v9._bayesian_db import (
    ContextKey,
    _parse_principles,
    _session_from_timestamp,
)

logger = logging.getLogger("v9.kelly_sizing")


class KellySizingEngine:
    """Câblage du multiplicateur Kelly bayésien-borné dans la chaîne de sizing.

    Composition avec DynamicRiskManager (multiplicatif) :
        final_size = base_size × dynamic_risk_multiplier × kelly_multiplier

    Le multiplicateur Kelly est dans [floor, cap] = [0.3, 2.0] par défaut.
    `compute_multiplier` retourne un multiplicateur de 1.0 (neutre) si :
      - Pas de posterior exploitable (n < MIN_N = 20)
      - posterior.prob_above(0.5) < MIN_PROB_ABOVE (0.6) → edge non confirmé
      - Kelly ≤ 0 (pas d'edge positif) → None côté calibrator
      - Erreur DB / scipy off / inattendue → log ERROR + neutre (R6 fail-safe)

    Lecture seule DB (mode=ro, via BayesianCalibrator). Aucune écriture.
    """

    DEFAULT_FLOOR = 0.3
    DEFAULT_CAP = 2.0
    DEFAULT_FRACTION = 0.25  # quart-Kelly conservateur
    DEFAULT_RR = 1.0         # reward/risk ratio estimé (TP/SL)
    MIN_N = 20               # n minimum pour activer le sizing
    MIN_PROB_ABOVE = 0.6     # edge confirmé (P(WR > 0.5))

    def __init__(self, calibrator: BayesianCalibrator, db_path: Path | str) -> None:
        self.calibrator = calibrator
        self.db_path = Path(db_path)

    def compute_multiplier(
        self,
        context_key: ContextKey | tuple,
        rr: float = DEFAULT_RR,
        fraction: float = DEFAULT_FRACTION,
        floor: float = DEFAULT_FLOOR,
        cap: float = DEFAULT_CAP,
    ) -> dict:
        """Calcule le multiplicateur Kelly pour un contexte donné.

        Le kill switch n'est **pas** vérifié ici : `compute_multiplier` est un
        calcul pur (utilisable par le smoke / l'analyse même quand la promotion
        ACTIVE est OFF). L'application effective au sizing est gardée par le
        kill switch dans `apply_kelly_to_sizing` / le hook `trade_engine`.

        Returns:
            dict {
                'multiplier': float,        # dans [floor, cap], 1.0 si neutre
                'applied': bool,            # False si conditions non remplies
                'reason': str,              # 'applied' | raison si neutre
                'posterior': dict | None,   # {alpha, beta, n, mean, prob_above_0_5}
                'kelly_full': float,        # Kelly brut f_full (info)
                'kelly_fractional': float,  # f_full × fraction (info)
                'rr_used': float,
                'fraction_used': float,
            }
        """
        result: dict = {
            "multiplier": 1.0,
            "applied": False,
            "reason": "not_computed",
            "posterior": None,
            "kelly_full": 0.0,
            "kelly_fractional": 0.0,
            "rr_used": rr,
            "fraction_used": fraction,
        }

        # 1. Posterior via le calibrator (lecture DB déléguée, cache interne).
        try:
            posterior = self.calibrator.fit_context(context_key)
        except Exception as exc:  # R6 — fail-safe neutre.
            result["reason"] = f"error:{exc}"
            logger.error(
                "kelly_sizing: fit_context failed for %s: %s", context_key, exc
            )
            return result

        prob_above = posterior.prob_above(0.5)
        result["posterior"] = {
            "alpha": posterior.alpha,
            "beta": posterior.beta,
            "n": posterior.n,
            "mean": posterior.mean,
            "prob_above_0_5": prob_above,
        }

        # 2. Garde-fous d'échantillon et d'edge (miroir du calibrator, pour
        #    produire une raison lisible avant l'appel Kelly).
        if posterior.n < self.MIN_N:
            result["reason"] = f"n_below_min ({posterior.n}<{self.MIN_N})"
            return result
        if prob_above < self.MIN_PROB_ABOVE:
            result["reason"] = (
                f"edge_unconfirmed (P={prob_above:.3f}<{self.MIN_PROB_ABOVE})"
            )
            return result

        # 3. Multiplicateur Kelly fractionnel borné (calibrator, math pure).
        try:
            multiplier = self.calibrator.kelly_fraction(
                posterior, rr=rr, fraction=fraction, floor=floor, cap=cap
            )
        except Exception as exc:  # R6 — fail-safe neutre.
            result["reason"] = f"error:{exc}"
            logger.error(
                "kelly_sizing: kelly_fraction failed for %s: %s", context_key, exc
            )
            return result

        if multiplier is None:
            # n / edge déjà validés au-dessus → seul cas restant : f_full ≤ 0
            # ou rr/fraction invalides (pas d'edge positif exploitable).
            result["reason"] = "no_positive_edge"
            return result

        # 4. Détails informatifs (Kelly brut, quart-Kelly) + application.
        p = posterior.mean
        q = 1.0 - p
        f_full = (p * rr - q) / rr if rr > 0 else 0.0
        result["kelly_full"] = f_full
        result["kelly_fractional"] = f_full * fraction
        result["multiplier"] = multiplier
        result["applied"] = True
        result["reason"] = "applied"
        logger.info(
            "kelly_sizing: applied mult=%.3f (n=%d mean=%.3f P>0.5=%.3f "
            "rr=%.2f frac=%.2f) ctx=%s",
            multiplier, posterior.n, p, prob_above, rr, fraction, context_key,
        )
        return result

    def is_enabled(self) -> bool:
        """Lit le kill switch V9_KELLY_FRACTIONAL_ENABLED (défaut OFF, R25').

        Fail-safe : toute erreur d'import / lecture → OFF (R6)."""
        try:
            from core.v9.kill_switches import is_enabled
            return is_enabled("V9_KELLY_FRACTIONAL_ENABLED")
        except Exception:
            return False


# ── Point d'extension trade_engine : application au sizing ────────────────
def apply_kelly_to_sizing(
    base_size: float,
    kelly_engine: KellySizingEngine | None,
    context_key: ContextKey | tuple,
    dynamic_risk_multiplier: float = 1.0,
) -> dict:
    """Applique le multiplicateur Kelly au sizing (composition multiplicative).

        final_size = base_size × dynamic_risk_multiplier × kelly_multiplier

    Si `kelly_engine` est absent, le kill switch est OFF, ou l'edge n'est pas
    confirmé → `kelly_multiplier = 1.0` (neutre) : `final_size` vaut alors
    `base_size × dynamic_risk_multiplier` (zéro régression vs l'existant).

    Returns:
        dict {
            'final_size': float,
            'base_size': float,
            'dynamic_risk_multiplier': float,
            'kelly_multiplier': float,     # dans [floor, cap] si appliqué, sinon 1.0
            'applied': bool,
            'report': dict | None,         # sortie compute_multiplier si évalué
        }
    """
    kelly_multiplier = 1.0
    applied = False
    report: dict | None = None

    if kelly_engine is not None and kelly_engine.is_enabled():
        report = kelly_engine.compute_multiplier(context_key)
        if report.get("applied"):
            kelly_multiplier = float(report["multiplier"])
            applied = True

    return {
        "final_size": base_size * dynamic_risk_multiplier * kelly_multiplier,
        "base_size": base_size,
        "dynamic_risk_multiplier": dynamic_risk_multiplier,
        "kelly_multiplier": kelly_multiplier,
        "applied": applied,
        "report": report,
    }


def build_context_key(db_path: Path | str, snapshot_id: str) -> ContextKey | None:
    """Reconstruit la clé de contexte Kelly d'un snapshot depuis `decisions`.

    Clé = (principle, symbol, timeframe, session, regime) — mêmes conventions
    que `_bayesian_db.read_context_aggregates` (principe primaire = 1er élément
    de `principes_json`, session dérivée du timestamp, regime = `regime_type`).
    Lecture seule (mode=ro). R6 : retourne None sur toute erreur / donnée absente.
    """
    try:
        uri = f"file:{Path(db_path).as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        logger.error("kelly_sizing: DB inaccessible pour context_key (%s)", exc)
        return None
    try:
        row = conn.execute(
            "SELECT principes_json, symbol, timeframe, regime_type, timestamp "
            "FROM decisions WHERE snapshot_id = ? ORDER BY timestamp DESC LIMIT 1",
            (snapshot_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        logger.error("kelly_sizing: lecture context_key échouée (%s)", exc)
        return None
    finally:
        conn.close()

    if row is None:
        return None
    principles = _parse_principles(row["principes_json"])
    if not principles:
        return None
    principle = principles[0]
    symbol = row["symbol"] or "?"
    timeframe = row["timeframe"] or "?"
    session = _session_from_timestamp(row["timestamp"])
    regime = row["regime_type"] or "inconnu"
    return (principle, symbol, timeframe, session, regime)

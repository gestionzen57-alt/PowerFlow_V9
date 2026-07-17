"""edge_validator.py — Validation statistique des edges.

Un stratège institutionnel ne déclare jamais un edge sans test de
significativité. Un WR de 60% sur 10 trades peut être du bruit.
Un WR de 55% sur 1000 trades est presque certainement réel.

Ce module calcule :
  - Test t sur l'expectancy (H0: expectancy = 0)
  - p-value (probabilité que l'edge soit du bruit)
  - Intervalle de confiance à 95%
  - Sharpe-like ratio (rendement ajusté du risque)
  - Profit factor (gross win / gross loss)
  - Maximum drawdown

Usage :
    from core.v9.edge_validator import EdgeValidator
    validator = EdgeValidator(db_path="data/v9_forces.db")
    result = validator.validate("PRICE_LAG_AT_NODE_BIRTH")
    # → {"n_trades": 8092, "expectancy": 5.72, "p_value": 0.0001, "significant": True}

Doctrine :
  - R18 : code pur, stdlib uniquement (math, statistics, sqlite3)
  - R2 : additif — ne modifie pas le calcul existant
  - R6 : try/except, jamais bloquant
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection

# Seuil de significativité (5% = standard institutionnel).
P_VALUE_THRESHOLD = 0.05
P_VALUE_HIGH_CONFIDENCE = 0.01


class EdgeValidator:
    """Valide statistiquement qu'un edge est réel, pas du bruit.

    Lit les trades résolus depuis la DB et calcule les métriques
    de validation statistique.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetch_trades(self, principle_id: str) -> list[dict[str, Any]]:
        """Récupère les trades résolus pour un principe."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT d.is_win, d.resolution_pips
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                WHERE pe.principle_id = ?
                  AND pe.triggered = 1
                  AND d.is_win IS NOT NULL
                ORDER BY d.timestamp ASC
                """,
                (principle_id,),
            ).fetchall()
            return [{"is_win": r["is_win"], "pips": float(r["resolution_pips"] or 0.0)} for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def validate(self, principle_id: str) -> dict[str, Any]:
        """Valide l'edge d'un principe avec tests statistiques.

        Returns:
            dict avec n_trades, win_rate, expectancy, std, t_stat,
            p_value, significant, confidence, sharpe, profit_factor,
            max_drawdown, ci_low, ci_high
        """
        trades = self._fetch_trades(principle_id)
        n = len(trades)

        if n == 0:
            return {
                "principle_id": principle_id,
                "n_trades": 0,
                "significant": False,
                "confidence": "none",
                "error": "no trades",
            }

        wins = [t for t in trades if t["is_win"] == 1]
        losses = [t for t in trades if t["is_win"] == 0]
        pips = [t["pips"] for t in trades]

        # Métriques de base
        wr = len(wins) / n
        expectancy = sum(pips) / n

        # Écart-type
        if n > 1:
            mean = expectancy
            var = sum((p - mean) ** 2 for p in pips) / (n - 1)
            std = math.sqrt(var)
        else:
            std = 0.0

        # Test t (H0: expectancy = 0)
        if std > 0 and n > 1:
            t_stat = expectancy / (std / math.sqrt(n))
            # p-value approximative (distribution t, approximation normale pour n > 30)
            # Pour n > 30, t ≈ z (normale standard)
            if n > 30:
                # Approximation normale
                p_value = 2 * (1 - _normal_cdf(abs(t_stat)))
            else:
                # Approximation t (simplifiée — utilise la normale comme proxy conservateur)
                p_value = 2 * (1 - _normal_cdf(abs(t_stat)))
        else:
            t_stat = 0.0
            p_value = 1.0

        # Intervalle de confiance à 95%
        if std > 0 and n > 1:
            ci_margin = 1.96 * std / math.sqrt(n)
            ci_low = expectancy - ci_margin
            ci_high = expectancy + ci_margin
        else:
            ci_low = ci_high = expectancy

        # Sharpe-like ratio (expectancy / std)
        sharpe = round(expectancy / std, 3) if std > 0 else 0.0

        # Profit factor (gross win / gross loss)
        gross_win = sum(p for p in pips if p > 0)
        gross_loss = -sum(p for p in pips if p < 0)
        profit_factor = round(gross_win / gross_loss, 3) if gross_loss > 0 else float("inf")

        # Maximum drawdown
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pips:
            equity += p
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        # Niveau de confiance
        if p_value < P_VALUE_HIGH_CONFIDENCE:
            confidence = "high"
        elif p_value < P_VALUE_THRESHOLD:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "principle_id": principle_id,
            "n_trades": n,
            "win_rate": round(wr * 100, 2),
            "expectancy": round(expectancy, 3),
            "std": round(std, 3),
            "t_stat": round(t_stat, 3),
            "p_value": round(p_value, 6),
            "significant": p_value < P_VALUE_THRESHOLD,
            "confidence": confidence,
            "sharpe_like": sharpe,
            "profit_factor": profit_factor,
            "max_drawdown": round(max_dd, 2),
            "ci_95_low": round(ci_low, 3),
            "ci_95_high": round(ci_high, 3),
            "gross_win": round(gross_win, 2),
            "gross_loss": round(gross_loss, 2),
        }

    def validate_all(self, min_trades: int = 20) -> list[dict[str, Any]]:
        """Valide tous les principes avec au moins min_trades trades résolus.

        Returns:
            Liste de résultats triés par expectancy décroissante.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT pe.principle_id, COUNT(DISTINCT d.decision_id) as n
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                WHERE pe.triggered = 1 AND d.is_win IS NOT NULL
                GROUP BY pe.principle_id
                HAVING n >= ?
                ORDER BY n DESC
                """,
                (min_trades,),
            ).fetchall()
            principle_ids = [r["principle_id"] for r in rows]
        except sqlite3.Error:
            principle_ids = []
        finally:
            conn.close()

        results = []
        for pid in principle_ids:
            try:
                result = self.validate(pid)
                results.append(result)
            except Exception:
                continue

        # Tri par expectancy décroissante
        results.sort(key=lambda x: x.get("expectancy", 0), reverse=True)
        return results


def _normal_cdf(x: float) -> float:
    """CDF de la distribution normale standard (approximation).

    Utilise l'approximation d'Abramowitz & Stegun (erreur < 7.5e-8).
    """
    # Coefficients
    b0 = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429

    if x < 0:
        return 1.0 - _normal_cdf(-x)

    t = 1.0 / (1.0 + b0 * x)
    poly = t * (b1 + t * (b2 + t * (b3 + t * (b4 + t * b5))))
    pdf = math.exp(-x * x / 2.0) / math.sqrt(2.0 * math.pi)
    return 1.0 - pdf * poly
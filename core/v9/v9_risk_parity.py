"""v9_risk_parity.py — Risk Parity multi-paires hedge fund.

2026-07-17 motion CEO « orchestre et optimise au max, hedge fund mondial ».

Risk Parity =分配 capital proportionnellement au risque (variance), pas
au nominal. Standard chez AQR, Bridgewater.

Appliqué à V9 :
  - 5 paires actives (GBPUSD, USDJPY, USDCAD, USDCHF, EURUSD)
  - USDCAD blacklisté (WR < 30%)
  - Risk budget par paire = 1/N (risk parity stricte)
  - Vol targeting : 15% annualisé cible
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.db_schema import get_connection

log = logging.getLogger(__name__)

RISK_PARITY_VERSION = "1.0"

# Blacklist hard (motion CEO 2026-07-17 + bilan 7j 2026-07-22)
# USDCAD : WR 15.8% confirmé
# AUDUSD : WR 35.9% -239 pips (bilan 7j)
# USDJPY : WR 49.4% -274 pips (pire avg pips/trade)
HARD_BLACKLIST = {"USDCAD", "AUDUSD", "USDJPY"}


@dataclass
class PairRiskBudget:
    """Budget de risque alloué à une paire."""
    symbol: str
    risk_weight: float  # 0..1, somme = 1.0
    vol_annualized: float  # vol estimée annualisée
    expected_sharpe: float  # sharpe attendu historique
    max_position_size: float  # position max en lots
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "risk_weight": self.risk_weight,
            "vol_annualized": self.vol_annualized,
            "expected_sharpe": self.expected_sharpe,
            "max_position_size": self.max_position_size,
            "rationale": self.rationale,
        }


def estimate_vol_annualized(
    db_path: Path | str | None, symbol: str, lookback_bars: int = 1000,
    min_bars: int = 20,
) -> float:
    """Estime la volatilité annualisée d'une paire depuis les returns.

    Returns: vol annualisée en pips annualisés (ex 800 = 8% du pip typique).
    Ou -1.0 si pas assez de data (sentinel).

    Convention : on retourne la vol en pips annualisés (et non en % return).
    Les fonds quantiques utilisent typiquement 500-1500 pips annualisés
    pour les paires majeures. Une vol > 5000 = très volatile.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT mid FROM forces_snapshots "
            "WHERE symbol = ? AND timeframe = 'M15' "
            "ORDER BY bar_time DESC LIMIT ?",
            (symbol, lookback_bars),
        ).fetchall()
    finally:
        conn.close()

    if len(rows) < min_bars:
        return -1.0

    prices = [r[0] for r in rows]
    mids = list(reversed(prices))
    if not mids or len(mids) < 2:
        return -1.0
    pip_mult = 100 if "JPY" in symbol else 10000
    returns_pips = [
        (mids[i] - mids[i - 1]) * pip_mult for i in range(1, len(mids))
    ]
    if not returns_pips:
        return -1.0

    mean_r = sum(returns_pips) / len(returns_pips)
    variance = sum((r - mean_r) ** 2 for r in returns_pips) / max(len(returns_pips) - 1, 1)
    stddev_per_bar = math.sqrt(variance)
    bars_per_year = 96 * 252
    vol_annualized_pips = stddev_per_bar * math.sqrt(bars_per_year)

    return round(vol_annualized_pips, 1)


def compute_expected_sharpe(
    db_path: Path | str | None, symbol: str, min_n: int = 10,
) -> float:
    """Estime le Sharpe ratio attendu historique pour une paire."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT
                AVG(pt.pips_simulated) AS avg_pips,
                COUNT(*) AS n,
                SQRT(AVG(pt.pips_simulated*pt.pips_simulated) - AVG(pt.pips_simulated)*AVG(pt.pips_simulated)) AS stddev
            FROM paper_trades pt
            JOIN decisions d ON d.snapshot_id = pt.snapshot_id
            WHERE pt.closed_at IS NOT NULL
              AND pt.pips_simulated IS NOT NULL
              AND d.symbol = ?
            """,
            (symbol,),
        ).fetchone()
    finally:
        conn.close()

    if not row or not row[1] or row[1] < min_n or not row[2] or row[2] == 0:
        return 0.0

    # Sharpe brut = avg / stddev (non annualisé)
    avg_pips = float(row[0] or 0)
    stddev = float(row[2])
    return round(avg_pips / stddev, 4) if stddev > 0 else 0.0


def compute_risk_parity_budgets(
    capital: float = 10000.0,
    target_vol: float = 0.15,
    db_path: Path | str | None = None,
    pairs: list[str] | None = None,
) -> list[PairRiskBudget]:
    """Calcule le budget de risque risk-parity pour chaque paire.

    Algorithme :
      1. Estime vol annualisée par paire
      2. Calcule expected Sharpe par paire
      3. Filtre les paires blacklistées
      4. Risk weight ∝ (1 / vol) × sharpe_max(0.5, sharpe)
      5. Normalise pour que la somme = 1.0
      6. Position size = (capital × risk_weight × target_vol) / vol_paire
    """
    if pairs is None:
        pairs = ["GBPUSD", "USDJPY", "USDCHF", "EURUSD", "AUDUSD", "NZDUSD"]
    pairs = [p for p in pairs if p not in HARD_BLACKLIST]

    raw_weights: list[tuple[str, float, float, float]] = []
    for sym in pairs:
        vol = estimate_vol_annualized(db_path, sym)
        # Filtre sentinel (-1 = pas assez de data, on skip).
        # Aussi filtre vol > 5000 pips annualisés (outlier FX, doit être < 3000).
        if vol <= 0 or vol > 5000:
            log.debug("Skip %s: vol=%.1f hors plage", sym, vol)
            continue
        sharpe = compute_expected_sharpe(db_path, sym)
        # risk weight ∝ (1 / vol) × max(0.2, sharpe)  # ← Seuil minimal 0.2 (edge GBPUSD confirmé)
        score = (1.0 / vol) * max(0.2, sharpe)
        raw_weights.append((sym, score, vol, sharpe))

    # Filtrer les paires avec sharpe < 0.2 (edge GBPUSD confirmé)
    raw_weights = [(sym, score, vol, sharpe) for sym, score, vol, sharpe in raw_weights if sharpe >= 0.2]
    
    # Normalisation
    total = sum(w[1] for w in raw_weights) or 1.0
    budgets: list[PairRiskBudget] = []
    for sym, score, vol, sharpe in raw_weights:
        weight = score / total
        # Position size = capital × risk_weight × target_pips / vol_pips
        # target_vol annualisé en pips (ex 8000 = équivalent ~80% return).
        target_vol_pips = target_vol * 10000
        position = (capital * weight * target_vol_pips) / max(vol, 1)
        rationale = (
            f"vol={vol:.0f} pips/an sharpe={sharpe:.2f} → weight={weight*100:.1f}%"
        )
        budgets.append(PairRiskBudget(
            symbol=sym,
            risk_weight=round(weight, 4),
            vol_annualized=vol,
            expected_sharpe=sharpe,
            max_position_size=round(position, 0),
            rationale=rationale,
        ))

    return budgets


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Risk Parity multi-paires V9")
    parser.add_argument("--capital", type=float, default=10000.0)
    parser.add_argument("--target-vol", type=float, default=0.15)
    parser.add_argument("--pairs", nargs="+", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    budgets = compute_risk_parity_budgets(
        capital=args.capital,
        target_vol=args.target_vol,
        pairs=args.pairs,
    )
    print(json.dumps({
        "version": RISK_PARITY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "capital": args.capital,
        "target_vol_annualized": args.target_vol,
        "blacklist": list(HARD_BLACKLIST),
        "budgets": [b.to_dict() for b in budgets],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


class RiskParityEngine:
    """Wrapper pour Risk Parity - interface orientée objet pour trade_engine.
    
    Délègue à compute_risk_parity_budgets() qui implémente la logique
    AQR/Bridgewater standard (weight ∝ 1/vol × max(0.5, sharpe)).
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path

    def compute_budgets(
        self,
        capital: float = 10000.0,
        target_vol: float = 0.15,
        pairs: list[str] | None = None,
    ) -> list[PairRiskBudget]:
        """Calcule les budgets risk-parity pour le capital donné."""
        return compute_risk_parity_budgets(
            capital=capital,
            target_vol=target_vol,
            db_path=self.db_path,
            pairs=pairs,
        )
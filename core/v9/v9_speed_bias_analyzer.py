"""v9_speed_bias_analyzer.py — Analyse asymétrie vitesse haussier vs baissier.

2026-07-17 motion CEO « le trend baissier est plus rapide dans la baisse est
ca que la lecture des time frame > est pas biaisai par le temps qui lisse ».

Module d'analyse qui révèle l'asymétrie des mouvements par timeframe.

Découvertes initiales :
  - P95 haussier M5 (1 barre) = +6.50 pips
  - P95 baissier M5 (1 barre) = -0.60 pips (!)
  - Force moyenne quasi identique (~2.3 pips)
  - Mais les SPIKES baissiers sont concentrés sur TRÈS peu de barres
  - Le M15 lisse ces spikes → le système détecte le MOVE APRÈS qu'il soit passé

Doctrine R6 : try/except défensif. R18 : pas de LLM.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.db_schema import get_connection

log = logging.getLogger(__name__)

SPEED_BIAS_VERSION = "1.0"


@dataclass
class BarMovementStats:
    """Stats de mouvement par barre pour une direction donnée."""
    n_bars: int
    avg_delta_pips: float
    median_delta_pips: float
    p95_delta_pips: float  # valeur extrême P95
    p99_delta_pips: float
    avg_force_pips: float  # moyenne de |delta|
    max_delta_pips: float
    avg_duration_bars: float  # durée moyenne d'un run directionnel

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class SpeedBiasReport:
    """Rapport de biais de vitesse haussier vs baissier."""
    symbol: str
    timeframe: str
    sample_size: int
    bullish: BarMovementStats
    bearish: BarMovementStats
    bear_to_bull_ratio: float  # ratio P95 bearish / P95 bullish

    @property
    def is_bearish_faster(self) -> bool:
        """True si bearish plus rapide que bullish en magnitude P95."""
        return abs(self.bearish.p95_delta_pips) > abs(self.bullish.p95_delta_pips)

    @property
    def recommendation(self) -> str:
        if self.is_bearish_faster:
            return (
                "MOUVEMENT BAISSIER PLUS RAPIDE détecté. "
                "Adapter la lecture : utiliser TF inférieurs (M1/tick) pour baissier. "
                "TP=2-4 pips, time_exit=1-2 barres M5."
            )
        return "Pas de biais significatif détecté."

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "sample_size": self.sample_size,
            "bullish": self.bullish.to_dict() if isinstance(self.bullish, BarMovementStats) else self.bullish,
            "bearish": self.bearish.to_dict() if isinstance(self.bearish, BarMovementStats) else self.bearish,
            "bear_to_bull_ratio": self.bear_to_bull_ratio,
            "is_bearish_faster": self.is_bearish_faster,
            "recommendation": self.recommendation,
        }


class SpeedBiasAnalyzer:
    """Analyseur de biais de vitesse sur mouvements M5/M1/etc."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path

    def analyze_timeframe(
        self, *, symbol: str, timeframe: str = "M5", lookback_bars: int = 5000
    ) -> SpeedBiasReport:
        """Analyse l'asymétrie de vitesse pour un symbol/TF donné."""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT close, open FROM forces_snapshots
                WHERE symbol = ? AND timeframe = ?
                ORDER BY bar_time DESC LIMIT ?
                """,
                (symbol, timeframe, lookback_bars),
            ).fetchall()
        finally:
            conn.close()

        if len(rows) < 100:
            raise ValueError(f"Pas assez de données pour {symbol} {timeframe}: {len(rows)} bars")

        # Inverser pour chronologique
        rows = list(reversed(rows))

        # Calcule delta par barre
        bull_deltas = []
        bear_deltas = []
        bull_runs = []
        bear_runs = []
        current_run = []
        current_dir = 0  # +1 bull, -1 bear

        for i in range(0, len(rows) - 1):
            try:
                delta = (float(rows[i + 1]["close"]) - float(rows[i]["close"])) * 10000
            except (TypeError, ValueError):
                continue

            if delta > 0.5:
                bull_deltas.append(delta)
                if current_dir == -1:
                    if current_run:
                        bear_runs.append(len(current_run))
                    current_run = [delta]
                elif current_dir == 1:
                    current_run.append(delta)
                else:
                    current_run = [delta]
                current_dir = 1
            elif delta < -0.5:
                bear_deltas.append(delta)
                if current_dir == 1:
                    if current_run:
                        bull_runs.append(len(current_run))
                    current_run = [delta]
                elif current_dir == -1:
                    current_run.append(delta)
                else:
                    current_run = [delta]
                current_dir = -1
            else:
                # Pause → close run
                if current_run and current_dir == 1:
                    bull_runs.append(len(current_run))
                elif current_run and current_dir == -1:
                    bear_runs.append(len(current_run))
                current_run = []
                current_dir = 0

        # Close le dernier run
        if current_run:
            if current_dir == 1:
                bull_runs.append(len(current_run))
            elif current_dir == -1:
                bear_runs.append(len(current_run))

        def _stats(deltas: list[float], runs: list[int]) -> BarMovementStats:
            if not deltas:
                return BarMovementStats(0, 0, 0, 0, 0, 0, 0, 0)
            sorted_d = sorted(deltas)
            n = len(deltas)
            return BarMovementStats(
                n_bars=n,
                avg_delta_pips=round(sum(deltas) / n, 2),
                median_delta_pips=round(sorted_d[n // 2], 2),
                p95_delta_pips=round(sorted_d[int(0.95 * n)], 2),
                p99_delta_pips=round(sorted_d[int(0.99 * n)], 2),
                avg_force_pips=round(sum(abs(d) for d in deltas) / n, 2),
                max_delta_pips=round(max(deltas), 2),
                avg_duration_bars=round(sum(runs) / len(runs), 1) if runs else 0,
            )

        bull_stats = _stats(bull_deltas, bull_runs)
        bear_stats = _stats(bear_deltas, bear_runs)

        ratio = 0.0
        if bull_stats.p95_delta_pips:
            ratio = abs(bear_stats.p95_delta_pips) / bull_stats.p95_delta_pips

        return SpeedBiasReport(
            symbol=symbol,
            timeframe=timeframe,
            sample_size=len(rows),
            bullish=bull_stats,
            bearish=bear_stats,
            bear_to_bull_ratio=round(ratio, 3),
        )

    def analyze_all(self) -> list[SpeedBiasReport]:
        """Analyse tous les symboles/TF disponibles."""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT symbol, timeframe FROM forces_snapshots WHERE timeframe IN ('M1','M5','M15')"
            ).fetchall()
        finally:
            conn.close()

        reports = []
        for r in rows:
            # r peut être tuple ou Row
            try:
                sym, tf = r["symbol"], r["timeframe"]
            except (TypeError, KeyError):
                sym, tf = r[0], r[1]
            try:
                rep = self.analyze_timeframe(symbol=sym, timeframe=tf)
                reports.append(rep)
            except Exception as exc:
                log.debug("Skip %s %s: %s", sym, tf, exc)
        return reports


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Speed bias analyzer V9")
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--timeframe", default="M5")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    analyzer = SpeedBiasAnalyzer()

    if args.all:
        reports = analyzer.analyze_all()
        print(f"Analyse {len(reports)} symbol/TF :")
        for r in reports:
            print(f"  {r.symbol:>8} {r.timeframe:>4} : "
                  f"bull P95={r.bullish.p95_delta_pips:+.2f}p "
                  f"bear P95={r.bearish.p95_delta_pips:+.2f}p "
                  f"ratio={r.bear_to_bull_ratio} "
                  f"bear_faster={r.is_bearish_faster}")
    else:
        rep = analyzer.analyze_timeframe(symbol=args.symbol, timeframe=args.timeframe)
        print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
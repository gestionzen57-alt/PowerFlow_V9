"""v9_monte_carlo.py — Simulateur Monte Carlo pour stress-test V9.

2026-07-17 motion CEO « orchestre et optimise au max, hedge fund mondial ».

Simule N itérations de trades aléatoires tirés depuis la distribution
historique des paper_trades, segmentée par principe × session × régime
(symbol déduit via snapshot_id -> forces_snapshots.symbol).

Le but : stress-tester la stratégie sur des centaines de chemins
possibles et mesurer la robustesse (drawdown attendu, probabilité
d'expectancy positive, intervalle de confiance du Sharpe).

Doctrine R6 : défensif sur chaque sous-étape (try/except + log).
Doctrine R18 : pas de LLM dans la boucle. Code pur stdlib + sqlite3.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sqlite3
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.db_schema import get_connection

log = logging.getLogger(__name__)

MONTE_CARLO_VERSION = "1.0"

# Scénarios de stress supportés.
# Chaque scénario applique un multiplicateur sur la vol et (optionnel) sur
# la moyenne des pips pour modéliser une altération du régime de marché.
STRESS_SCENARIOS: dict[str, dict[str, float]] = {
    "normal": {"vol_mult": 1.0, "mean_shift_pips": 0.0},
    "black_swan": {"vol_mult": 1.30, "mean_shift_pips": -3.0},  # +30% vol, -3 pips / trade
    "crisis": {"vol_mult": 1.50, "mean_shift_pips": -6.0},  # +50% vol, -6 pips / trade
}


@dataclass
class MonteCarloResult:
    """Résultat d'une simulation Monte Carlo.

    Toutes les grandeurs sont agrégées sur N itérations.
    mean_pips = moyenne de la somme de pips par simulation.
    proba_positive = % de simulations dont l'expectancy par trade > 0.
    """

    n_simulations: int
    n_trades_per_sim: int
    scenario: str
    mean_pips: float
    std_pips: float
    var_pips: float
    percentile_5: float
    percentile_50: float
    percentile_95: float
    max_drawdown_mean: float
    max_drawdown_p95: float
    sharpe_mean: float
    sharpe_p5: float
    proba_positive: float
    sample_size_source: int = 0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MonteCarloSimulator:
    """Simulateur Monte Carlo depuis la distribution historique des paper_trades.

    Le simulateur charge la distribution des pips_simulated depuis
    paper_trades (filtré par symbol via snapshot_id -> forces_snapshots.symbol,
    session, regime si fournis). Chaque itération tire n_trades au hasard
    avec remise et calcule :

      - somme des pips
      - max drawdown intra-simulation
      - Sharpe-like = mean / stddev (annualisé sqrt(N))

    Puis on agrège sur N itérations : moyenne, percentiles, proba_positive.
    """

    def __init__(
        self,
        n_simulations: int = 1000,
        lookback_trades: int = 1000,
        seed: int | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        if n_simulations <= 0:
            raise ValueError(f"n_simulations doit être > 0, reçu {n_simulations}")
        if lookback_trades <= 0:
            raise ValueError(f"lookback_trades doit être > 0, reçu {lookback_trades}")
        self.n_simulations = n_simulations
        self.lookback_trades = lookback_trades
        self.seed = seed
        self._rng = random.Random(seed)
        self.db_path = Path(db_path) if db_path else None

    # ── Chargement de la distribution historique ────────────────────

    def _load_distribution(
        self,
        *,
        symbol: str | None = None,
        session: str | None = None,
    ) -> list[float]:
        """Charge les pips_simulated historiques pour le segment demandé.

        Filtre :
          - symbol : via jointure paper_trades.snapshot_id -> forces_snapshots.symbol
          - session : via json_extract(risk_go_context, '$.session_marche')
        Tri DESC par closed_at, limité à lookback_trades.
        """
        conn = get_connection(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            sql = (
                "SELECT pt.pips_simulated "
                "FROM paper_trades pt "
                "LEFT JOIN forces_snapshots fs "
                "  ON fs.snapshot_id = pt.snapshot_id "
                "WHERE pt.closed_at IS NOT NULL "
            )
            params: list[Any] = []
            if symbol:
                sql += " AND fs.symbol = ? "
                params.append(symbol)
            if session:
                sql += " AND json_extract(pt.risk_go_context, '$.session_marche') = ? "
                params.append(session)
            sql += " ORDER BY pt.closed_at DESC LIMIT ? "
            params.append(self.lookback_trades)
            rows = conn.execute(sql, params).fetchall()
            return [float(r["pips_simulated"]) for r in rows if r["pips_simulated"] is not None]
        except sqlite3.Error as exc:
            log.error("[monte_carlo] erreur SQL _load_distribution: %s", exc)
            return []
        finally:
            try:
                conn.close()
            except Exception:  # R6
                pass

    # ── Simulation d'un chemin ──────────────────────────────────────

    def _simulate_one(
        self,
        distribution: list[float],
        n_trades: int,
        *,
        vol_mult: float = 1.0,
        mean_shift: float = 0.0,
    ) -> dict[str, float]:
        """Simule une trajectoire de n_trades tirés depuis la distribution.

        vol_mult : multiplie l'écart résiduel (pertes) tout en gardant les
                   gains à leur niveau nominal — modèle grossier mais
                   conservateur d'un stress "vol up".
        mean_shift : translation appliquée à chaque trade (modélise un drift).
        """
        if not distribution:
            return {"sum_pips": 0.0, "max_dd": 0.0, "sharpe": 0.0}

        # Tirage avec remise
        sampled = [self._rng.choice(distribution) for _ in range(n_trades)]
        # Stress-test : les pertes sont amplifiées, les gains gardés,
        # et on applique le drift uniforme.
        adjusted: list[float] = []
        for x in sampled:
            if x < 0:
                adjusted.append(x * vol_mult + mean_shift)
            else:
                adjusted.append(x + mean_shift)

        # Cumul + drawdown intra-simulation
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for x in adjusted:
            cum += x
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        # Sharpe-like par simulation (non annualisé, sqrt(N))
        if len(adjusted) > 1:
            mu = statistics.fmean(adjusted)
            sigma = statistics.pstdev(adjusted)
            sharpe = (mu / sigma) * math.sqrt(len(adjusted)) if sigma > 0 else 0.0
        else:
            sharpe = 0.0

        return {"sum_pips": cum, "max_dd": max_dd, "sharpe": sharpe}

    # ── Agrégation sur N simulations ─────────────────────────────────

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        """Percentile (méthode linéaire, pas de numpy)."""
        if not values:
            return 0.0
        s = sorted(values)
        k = (len(s) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return float(s[int(k)])
        return float(s[f] + (s[c] - s[f]) * (k - f))

    def _aggregate(
        self,
        per_sim: list[dict[str, float]],
        scenario: str,
        n_trades: int,
        sample_size: int,
    ) -> MonteCarloResult:
        sums = [s["sum_pips"] for s in per_sim]
        dds = [s["max_dd"] for s in per_sim]
        sharpes = [s["sharpe"] for s in per_sim]

        mean_pips = statistics.fmean(sums) if sums else 0.0
        std_pips = statistics.pstdev(sums) if len(sums) > 1 else 0.0
        var_pips = std_pips * std_pips

        p5 = self._percentile(sums, 5)
        p50 = self._percentile(sums, 50)
        p95 = self._percentile(sums, 95)

        max_dd_mean = statistics.fmean(dds) if dds else 0.0
        max_dd_p95 = self._percentile(dds, 95)

        sharpe_mean = statistics.fmean(sharpes) if sharpes else 0.0
        sharpe_p5 = self._percentile(sharpes, 5)

        # proba expectancy > 0 (par trade)
        proba = (
            100.0 * sum(1 for s in sums if s > 0) / len(sums) if sums else 0.0
        )

        return MonteCarloResult(
            n_simulations=len(per_sim),
            n_trades_per_sim=n_trades,
            scenario=scenario,
            mean_pips=round(mean_pips, 2),
            std_pips=round(std_pips, 2),
            var_pips=round(var_pips, 2),
            percentile_5=round(p5, 2),
            percentile_50=round(p50, 2),
            percentile_95=round(p95, 2),
            max_drawdown_mean=round(max_dd_mean, 2),
            max_drawdown_p95=round(max_dd_p95, 2),
            sharpe_mean=round(sharpe_mean, 3),
            sharpe_p5=round(sharpe_p5, 3),
            proba_positive=round(proba, 2),
            sample_size_source=sample_size,
        )

    # ── API publique ────────────────────────────────────────────────

    def simulate(
        self,
        *,
        symbol: str | None = None,
        session: str | None = None,
        n_trades: int = 100,
    ) -> MonteCarloResult:
        """Simule n_simulations × n_trades tirés depuis la distribution historique.

        Args:
            symbol : ex. 'GBPUSD' (None = tous)
            session : 'new_york' / 'overlap' / 'asie' (None = tous)
            n_trades : taille de chaque trajectoire simulée.
        """
        if n_trades <= 0:
            raise ValueError(f"n_trades doit être > 0, reçu {n_trades}")

        distribution = self._load_distribution(symbol=symbol, session=session)
        if not distribution:
            log.warning(
                "[monte_carlo] aucune distribution chargée (symbol=%s session=%s) — "
                "renvoi d'un résultat vide.",
                symbol,
                session,
            )
            return MonteCarloResult(
                n_simulations=0,
                n_trades_per_sim=n_trades,
                scenario="empty",
                mean_pips=0.0,
                std_pips=0.0,
                var_pips=0.0,
                percentile_5=0.0,
                percentile_50=0.0,
                percentile_95=0.0,
                max_drawdown_mean=0.0,
                max_drawdown_p95=0.0,
                sharpe_mean=0.0,
                sharpe_p5=0.0,
                proba_positive=0.0,
                sample_size_source=0,
            )

        per_sim: list[dict[str, float]] = []
        for _ in range(self.n_simulations):
            try:
                per_sim.append(self._simulate_one(distribution, n_trades))
            except Exception as exc:  # R6
                log.error("[monte_carlo] erreur _simulate_one: %s", exc)
                continue

        return self._aggregate(
            per_sim,
            scenario="custom",
            n_trades=n_trades,
            sample_size=len(distribution),
        )

    def stress_test(
        self,
        *,
        scenario: str = "black_swan",
        symbol: str | None = None,
        session: str | None = None,
        n_trades: int = 100,
    ) -> MonteCarloResult:
        """Stress-test avec scénario prédéfini.

        Scénarios supportés (cf. STRESS_SCENARIOS) :
          - 'normal'     : vol × 1.0, drift 0  (baseline)
          - 'black_swan' : vol × 1.30, drift -3 pips
          - 'crisis'     : vol × 1.50, drift -6 pips
        """
        cfg = STRESS_SCENARIOS.get(scenario)
        if cfg is None:
            log.warning(
                "[monte_carlo] scénario inconnu '%s', fallback 'normal' "
                "(disponibles: %s)",
                scenario,
                list(STRESS_SCENARIOS.keys()),
            )
            cfg = STRESS_SCENARIOS["normal"]
            scenario = "normal"

        distribution = self._load_distribution(symbol=symbol, session=session)
        if not distribution:
            log.warning(
                "[monte_carlo] aucune distribution pour stress_test "
                "(symbol=%s session=%s).",
                symbol,
                session,
            )
            return MonteCarloResult(
                n_simulations=0,
                n_trades_per_sim=n_trades,
                scenario=scenario,
                mean_pips=0.0,
                std_pips=0.0,
                var_pips=0.0,
                percentile_5=0.0,
                percentile_50=0.0,
                percentile_95=0.0,
                max_drawdown_mean=0.0,
                max_drawdown_p95=0.0,
                sharpe_mean=0.0,
                sharpe_p5=0.0,
                proba_positive=0.0,
                sample_size_source=0,
            )

        per_sim: list[dict[str, float]] = []
        for _ in range(self.n_simulations):
            try:
                per_sim.append(
                    self._simulate_one(
                        distribution,
                        n_trades,
                        vol_mult=cfg["vol_mult"],
                        mean_shift=cfg["mean_shift_pips"],
                    )
                )
            except Exception as exc:  # R6
                log.error("[monte_carlo] stress_test _simulate_one: %s", exc)
                continue

        return self._aggregate(
            per_sim,
            scenario=scenario,
            n_trades=n_trades,
            sample_size=len(distribution),
        )


# ── CLI entry point ────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulateur Monte Carlo V9")
    parser.add_argument("--symbol", default=None, help="Filtre par symbole (ex GBPUSD)")
    parser.add_argument("--session", default=None, help="Filtre par session (new_york, overlap, asie)")
    parser.add_argument("--n", type=int, default=100, help="Nombre de trades par simulation")
    parser.add_argument(
        "--simulations",
        type=int,
        default=1000,
        help="Nombre de simulations Monte Carlo",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=1000,
        help="Taille du lookback (trades historiques utilisés)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed RNG pour reproductibilité",
    )
    parser.add_argument(
        "--stress",
        choices=list(STRESS_SCENARIOS.keys()) + ["all"],
        default=None,
        help="Lance un stress-test au lieu d'une simulation normale",
    )
    args = parser.parse_args()

    sim = MonteCarloSimulator(
        n_simulations=args.simulations,
        lookback_trades=args.lookback,
        seed=args.seed,
    )

    if args.stress:
        scenarios = (
            list(STRESS_SCENARIOS.keys()) if args.stress == "all" else [args.stress]
        )
        results = []
        for sc in scenarios:
            try:
                r = sim.stress_test(
                    scenario=sc,
                    symbol=args.symbol,
                    session=args.session,
                    n_trades=args.n,
                )
                results.append(r)
            except Exception as exc:  # R6
                log.error("[monte_carlo] stress_test %s a échoué: %s", sc, exc)
                continue
    else:
        results = [
            sim.simulate(symbol=args.symbol, session=args.session, n_trades=args.n)
        ]

    print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""v9_paper_trade_mass.py — Backtest massif sur tous les candidats en attente.

2026-07-17 motion CEO « continue optimiser au max ».

Vide la file des décisions preparer_entree non encore tradées en un seul
processus long. Idempotent (peut être relancé sans rouvrir les trades
déjà fermés).

Usage :
    python scripts/v9_paper_trade_mass.py --limit 500
    python scripts/v9_paper_trade_mass.py --limit 1000 --quiet
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.trade_engine import TradeEngine  # noqa: E402


def setup_logging(quiet: bool = False) -> logging.Logger:
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("v9.paper_trade.mass")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest massif paper-trade")
    parser.add_argument(
        "--limit", type=int, default=500,
        help="Nombre de snapshots à traiter par batch (défaut 500)",
    )
    parser.add_argument(
        "--max-batches", type=int, default=0,
        help="Nombre max de batches (0 = illimité jusqu'à vider la file)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Moins de logs (WARNING uniquement)",
    )
    args = parser.parse_args()

    log = setup_logging(args.quiet)
    engine = TradeEngine()

    total_opened = 0
    total_closed = 0
    total_skipped = 0
    total_pips = 0.0
    total_wins = 0
    total_losses = 0
    batches = 0
    t0 = time.perf_counter()

    while True:
        if args.max_batches and batches >= args.max_batches:
            log.info("Limite batches atteinte (%d), arrêt.", args.max_batches)
            break

        remaining = engine._fetch_recent_snapshots(1)
        if not remaining:
            log.info("Plus de candidats en file. Arrêt.")
            break

        t_batch = time.perf_counter()
        summary = engine.run_batch(limit=args.limit)
        batches += 1
        elapsed = time.perf_counter() - t_batch

        total_opened += summary["opened"]
        total_closed += summary["closed"]
        total_skipped += summary["skipped"]
        total_wins += summary["wins"]
        total_losses += summary["losses"]

        log.info(
            "Batch %d (%.1fs) : opened=%d skipped=%d closed=%d (%dW/%dL WR=%.1f%%)",
            batches, elapsed,
            summary["opened"], summary["skipped"], summary["closed"],
            summary["wins"], summary["losses"], summary["wr"],
        )

        # Si le batch n'a rien fait, on arrête pour éviter boucle infinie
        if summary["opened"] == 0 and summary["closed"] == 0:
            log.info("Batch vide, arrêt.")
            break

    elapsed_total = time.perf_counter() - t0
    final_stats = engine.get_stats()

    log.info("=" * 60)
    log.info(
        "MASS BACKTEST TERMINÉ en %.1fs (%d batches)",
        elapsed_total, batches,
    )
    log.info(
        "Cumul batch : opened=%d skipped=%d closed=%d (%dW/%dL)",
        total_opened, total_skipped, total_closed,
        total_wins, total_losses,
    )
    log.info(
        "Stats globales : total=%d open=%d WR=%.1f%% pips=%.1f",
        final_stats["total"], final_stats["open"],
        final_stats["wr"], final_stats["total_pips"],
    )
    for direction, d in final_stats["by_direction"].items():
        log.info(
            "  %s: %dW/%d trades (WR=%.1f%%, pips=%.1f)",
            direction, d["wins"], d["total"], d["wr"], d.get("pips", 0),
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
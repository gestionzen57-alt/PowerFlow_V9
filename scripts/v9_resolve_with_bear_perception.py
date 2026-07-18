"""v9_resolve_with_bear_perception.py — Backtest de la correction baissière.

Mission baissier 2/2, Tâche 5. Re-résout les paper_trades baissiers
historiques en appliquant BearPerception (skip structurel + exit adaptatif) et
compare le résultat au trade original.

Pour chaque paper_trade baissier clôturé :
  1. Récupère prix d'entrée + prix futurs M5 (comme close_open_trades).
  2. Simule l'ORIGINAL (TP/SL enregistrés) via ExitSimulator.
  3. Applique BearPerception :
       - should_skip_bearish → le trade est SKIPPÉ (perte évitée si l'original
         perdait, coût si l'original gagnait).
       - sinon, si fast_move baissier détecté → simule avec le TP/SL de
         compute_fast_exit (would_exit).
       - sinon → identique à l'original.
  4. Agrège WR / avg_pips / would_skip / estimated_savings.

Sortie : data/strategy_pole/bear_perception_backtest.json

Doctrine :
  R6  — chaque trade est traité dans un try/except : un trade cassé n'arrête
        jamais le backtest.
  R18 — pur Python + sqlite3 (aucun LLM).
  R2  — lecture seule : n'écrit RIEN dans la DB, seulement le JSON de rapport.

CLI :
  uv run python scripts/v9_resolve_with_bear_perception.py
  uv run python scripts/v9_resolve_with_bear_perception.py --limit 500 --symbol GBPUSD
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import projet (chemin racine ajouté pour exécution directe).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.exit_simulator import (  # noqa: E402
    ExitSimulator,
    ExitStrategy,
    pips_multiplier_for_symbol,
)
from core.v9.v9_bear_perception import (  # noqa: E402
    DRIFT_SKIP_THRESHOLD_PIPS,
    BearAdaptiveStrategy,
    BearPerceptionCorrection,
)

OUTPUT_PATH = ROOT / "data" / "strategy_pole" / "bear_perception_backtest.json"


def _compute_drift_per_day(conn: sqlite3.Connection, symbol: str) -> float | None:
    """Drift journalier (pips/jour) proxy depuis les closes M5 récents (R6)."""
    try:
        rows = conn.execute(
            "SELECT bar_time, close FROM forces_snapshots "
            "WHERE symbol = ? AND timeframe = 'M5' AND stale = 0 "
            "ORDER BY bar_time DESC LIMIT 288",
            (symbol,),
        ).fetchall()
        if len(rows) < 2:
            return None
        pip_mult = pips_multiplier_for_symbol(symbol)
        newest_t, newest_c = rows[0][0], float(rows[0][1])
        oldest_t, oldest_c = rows[-1][0], float(rows[-1][1])
        span_days = max((newest_t - oldest_t) / 86400.0, 1e-9)
        return round((newest_c - oldest_c) * pip_mult / span_days, 2)
    except Exception:
        return None


def _future_mids(
    conn: sqlite3.Connection, symbol: str, opened_at: str, limit: int = 200,
) -> list[float]:
    """Prix futurs M5 après opened_at (R6 : liste vide si indisponible)."""
    try:
        opened_dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        opened_epoch = int(opened_dt.timestamp())
    except Exception:
        return []
    try:
        rows = conn.execute(
            "SELECT mid FROM forces_snapshots "
            "WHERE symbol = ? AND timeframe = 'M5' AND bar_time > ? "
            "ORDER BY bar_time ASC LIMIT ?",
            (symbol, opened_epoch, limit),
        ).fetchall()
        return [float(r[0]) for r in rows if r[0] is not None]
    except Exception:
        return []


def _simulate(
    symbol: str, direction: str, entry: float, future_mids: list[float],
    tp_pips: float, sl_pips: float, strategy_name: str,
) -> float | None:
    """Simule un trade, retourne les pips (ou None si non simulable)."""
    if not future_mids:
        return None
    try:
        strategy = ExitStrategy(strategy_name)
    except ValueError:
        strategy = ExitStrategy.TP_SL
    try:
        sim = ExitSimulator(
            strategy=strategy.value, tp_pips=tp_pips, sl_pips=sl_pips, symbol=symbol,
        )
        return sim.simulate(entry=entry, direction=direction, future_mids=future_mids).pips
    except Exception:
        return None


def run_backtest(
    db_path: Path | str | None = None,
    limit: int | None = None,
    symbol_filter: str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Re-résout les baissiers historiques avec BearPerception. Retourne le
    dict de métriques (et l'écrit dans OUTPUT_PATH si write=True)."""
    db = Path(db_path) if db_path else DB_PATH
    corrector = BearPerceptionCorrection(db)
    strategy = BearAdaptiveStrategy()

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    drift_cache: dict[str, float | None] = {}

    orig_pips: list[float] = []
    orig_wins = 0
    corr_pips: list[float] = []
    corr_wins = 0
    would_skip_count = 0
    estimated_savings_pips = 0.0
    n_seen = 0
    n_simulated = 0

    try:
        q = (
            "SELECT pt.trade_id, pt.snapshot_id, pt.opened_at, pt.pips_simulated, "
            "pt.is_win, d.decision_id, d.symbol, "
            "s.tp_pips_recommended, s.sl_pips_recommended, s.exit_strategy_recommended "
            "FROM paper_trades pt "
            "JOIN decisions d ON d.snapshot_id = pt.snapshot_id "
            "LEFT JOIN signals s ON s.snapshot_id = pt.snapshot_id "
            "WHERE pt.direction = 'baissiere' AND pt.closed_at IS NOT NULL "
        )
        params: list[Any] = []
        if symbol_filter:
            q += "AND d.symbol = ? "
            params.append(symbol_filter)
        q += "ORDER BY pt.opened_at DESC "
        if limit:
            q += "LIMIT ?"
            params.append(int(limit))
        rows = conn.execute(q, params).fetchall()

        for r in rows:
            n_seen += 1
            try:
                symbol = r["symbol"] or "GBPUSD"
                tp_pips = r["tp_pips_recommended"] or 8.0
                sl_pips = r["sl_pips_recommended"] or 15.0
                strat_name = r["exit_strategy_recommended"] or "DYNAMIC"

                future = _future_mids(conn, symbol, r["opened_at"] or "")
                if not future:
                    # Pas de prix futurs : on retombe sur les pips enregistrés.
                    original = float(r["pips_simulated"] or 0.0)
                else:
                    entry = future[0]
                    sim_pips = _simulate(
                        symbol, "baissiere", entry, future, tp_pips, sl_pips, strat_name,
                    )
                    original = sim_pips if sim_pips is not None else float(r["pips_simulated"] or 0.0)
                    n_simulated += 1

                orig_pips.append(original)
                if original > 0:
                    orig_wins += 1

                # ── BearPerception ──
                if symbol not in drift_cache:
                    drift_cache[symbol] = _compute_drift_per_day(conn, symbol)
                market_ctx = {"drift_pips_per_day": drift_cache[symbol]}

                would_skip = strategy.should_skip_bearish(
                    {"direction": "baissiere"}, market_ctx,
                )
                if would_skip:
                    would_skip_count += 1
                    # Perte évitée (savings > 0 si l'original perdait).
                    estimated_savings_pips += -original
                    # Le trade skippé ne compte pas dans la perf corrigée.
                    continue

                signal = corrector.detect_fast_movement(
                    symbol=symbol, decision_id=str(r["decision_id"] or r["snapshot_id"]),
                )
                if (
                    signal.is_fast_move
                    and signal.direction == "baissiere"
                    and future
                ):
                    vol_proxy = round(signal.m1_signal_strength * 3.0, 2)
                    fast_exit = strategy.compute_fast_exit(vol_pips=vol_proxy)
                    corrected = _simulate(
                        symbol, "baissiere", future[0], future,
                        fast_exit["tp_pips"], fast_exit["sl_pips"], "TP_SL",
                    )
                    corrected = corrected if corrected is not None else original
                else:
                    corrected = original

                corr_pips.append(corrected)
                if corrected > 0:
                    corr_wins += 1
            except Exception:
                # R6 — un trade cassé n'arrête jamais le backtest.
                continue
    finally:
        conn.close()

    n_orig = len(orig_pips)
    n_corr = len(corr_pips)
    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db),
        "symbol_filter": symbol_filter,
        "limit": limit,
        "drift_skip_threshold_pips": DRIFT_SKIP_THRESHOLD_PIPS,
        "n_baissier_seen": n_seen,
        "n_simulated_with_future": n_simulated,
        "win_rate_original": round(orig_wins / n_orig * 100, 2) if n_orig else 0.0,
        "win_rate_corrected": round(corr_wins / n_corr * 100, 2) if n_corr else 0.0,
        "avg_pips_original": round(sum(orig_pips) / n_orig, 3) if n_orig else 0.0,
        "avg_pips_corrected": round(sum(corr_pips) / n_corr, 3) if n_corr else 0.0,
        "total_pips_original": round(sum(orig_pips), 1),
        "total_pips_corrected_kept": round(sum(corr_pips), 1),
        "would_skip_count": would_skip_count,
        "n_corrected_kept": n_corr,
        "estimated_savings_pips": round(estimated_savings_pips, 1),
    }

    if write:
        try:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(
                json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8",
            )
            metrics["output_path"] = str(OUTPUT_PATH)
        except Exception as exc:  # R6 — l'écriture ne doit pas casser le run.
            metrics["write_error"] = str(exc)

    return metrics


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Backtest BearPerception sur les baissiers historiques.",
    )
    parser.add_argument("--db-path", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--symbol", type=str, default=None)
    parser.add_argument("--no-write", action="store_true", help="N'écrit pas le JSON.")
    args = parser.parse_args()

    metrics = run_backtest(
        db_path=args.db_path,
        limit=args.limit,
        symbol_filter=args.symbol,
        write=not args.no_write,
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())

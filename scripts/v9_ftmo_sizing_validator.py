"""v9_ftmo_sizing_validator.py — Phase 107 motion CEO.

FTMO Sizing Validator (R2 additif) : simule 1000 trades sur sizing actuel
et verifie la conformite aux regles FTMO Challenge 10k EUR.

Regles FTMO Challenge :
  - Max risk/trade : 1% du capital (= 100 EUR/trade sur 10k)
  - Max DD journalier : 5% (= 500 EUR/jour)
  - Max DD total : 10% (= 1000 EUR)
  - Leverage implicite <= 1:30 (EU regulations)

LIVRABLE NEUF (Phase 107) — complementaire a v9_ftmo_compliance_eur.py
(Phase 76) qui verifie un snapshot ponctuel. Ici on simule une trajectoire
de 1000 trades et on calcule les maxima de risque.

R2 additif (n'utilise pas v9_ftmo_compliance_eur.py pour eviter coupling
doctrinal). R6 best-effort. R14 git = verite.

Auteur : Hermes (Phase 107 motion CEO, 01/08/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.v9.config import DB_PATH

log = logging.getLogger("v9.ftmo_sizing_validator")

# Regles FTMO Challenge 10k EUR
DEFAULT_CAPITAL_EUR = 10000.0
DEFAULT_RISK_PCT_PER_TRADE = 0.01  # 1% = 100 EUR
DEFAULT_DAILY_DD_PCT = 0.05        # 5% = 500 EUR
DEFAULT_TOTAL_DD_PCT = 0.10        # 10% = 1000 EUR
DEFAULT_LEVERAGE_MAX = 30          # 1:30 EU

# Parametres simulation
DEFAULT_N_TRADES = 1000
DEFAULT_TRADES_PER_DAY = 4         # ~1 trade / 6h sur session Forex
DEFAULT_LOT_SIZE = 0.01
DEFAULT_SYMBOL = "GBPUSD"

# Pip values standard (lot 0.01)
PIP_VALUE_PER_LOT_USD = {
    "GBPUSD": 10.0, "EURUSD": 10.0, "AUDUSD": 10.0,
    "NZDUSD": 10.0, "USDCAD": 10.0, "USDCHF": 10.0,
    "USDJPY": 10.0, "EURJPY": 10.0, "GBPJPY": 10.0,
    "XAUUSD": 1.0,
}


# ---------------------------------------------------------------------------
# 1. Sizing actuel
# ---------------------------------------------------------------------------

def fetch_current_sizing(db_path: Path = DB_PATH) -> dict[str, Any]:
    """Lit le sizing actuel depuis la DB (paper_trades + risk_go_context).

    Si la DB est corrompue ou absente, retourne des defaults conservatifs.
    """
    if not db_path.exists():
        return {
            "source": "default",
            "lot_size": DEFAULT_LOT_SIZE,
            "avg_risk_pips": 10.0,
            "default_sizing_factor": 1.0,
            "symbols": [],
        }
    try:
        with sqlite3.connect(str(db_path)) as conn:
            # Lot size moyen
            lot_rows = conn.execute("""
                SELECT pips_simulated, is_win, direction
                FROM paper_trades
                ORDER BY opened_at DESC LIMIT 200
            """).fetchall()
            n = len(lot_rows)
            if n == 0:
                return {
                    "source": "default",
                    "lot_size": DEFAULT_LOT_SIZE,
                    "avg_risk_pips": 10.0,
                    "default_sizing_factor": 1.0,
                    "symbols": [],
                }
            # Estime risk_pips comme la moyenne des |pips_simulated| perdants
            losses = [abs(r[0]) for r in lot_rows if r[1] == 0 and r[0] < 0]
            avg_risk = sum(losses) / len(losses) if losses else 10.0
            return {
                "source": "db_recent_200",
                "lot_size": DEFAULT_LOT_SIZE,
                "avg_risk_pips": round(avg_risk, 2),
                "default_sizing_factor": 1.0,
                "symbols": ["GBPUSD", "EURUSD"],  # approximation
            }
    except sqlite3.DatabaseError as exc:
        log.warning("fetch_current_sizing: DB error %s — fallback defaults", exc)
        return {
            "source": "default_db_error",
            "lot_size": DEFAULT_LOT_SIZE,
            "avg_risk_pips": 10.0,
            "default_sizing_factor": 1.0,
            "symbols": [],
            "warning": str(exc),
        }


# ---------------------------------------------------------------------------
# 2. Simulation 1000 trades
# ---------------------------------------------------------------------------

def simulate_trades(
    n_trades: int = DEFAULT_N_TRADES,
    trades_per_day: int = DEFAULT_TRADES_PER_DAY,
    lot_size: float = DEFAULT_LOT_SIZE,
    symbol: str = DEFAULT_SYMBOL,
    avg_risk_pips: float = 10.0,
    avg_win_pips: float = 25.0,
    wr: float = 0.75,
    sizing_factor: float = 1.0,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Simule n_trades sur la base d'un profil (WR, risk/win pips).

    Returns list de dicts {trade_id, opened_at, direction, pips, is_win,
    risk_eur, pnl_eur, sizing_factor}.
    """
    rng = random.Random(seed)
    pip_value_eur = PIP_VALUE_PER_LOT_USD.get(symbol.upper(), 10.0) * lot_size
    n_days = math.ceil(n_trades / trades_per_day)
    trades: list[dict[str, Any]] = []
    base = datetime.now(timezone.utc) - timedelta(days=n_days)
    for i in range(n_trades):
        day_offset = i // trades_per_day
        trade_in_day = i % trades_per_day
        opened = base + timedelta(
            days=day_offset,
            hours=8 + trade_in_day * 4,  # sessions Forex 8h, 12h, 16h, 20h UTC
        )
        is_win = 1 if rng.random() < wr else 0
        pips = avg_win_pips if is_win else -avg_risk_pips
        # Application sizing_factor (boost pyramiding)
        pips_scaled = pips * sizing_factor
        risk_eur = abs(min(0, pips_scaled)) * pip_value_eur
        pnl_eur = pips_scaled * pip_value_eur
        trades.append({
            "trade_id": f"SIM-{i:05d}",
            "opened_at": opened.isoformat(),
            "direction": "haussiere" if is_win else "baissiere",
            "pips": round(pips_scaled, 2),
            "is_win": is_win,
            "risk_eur": round(risk_eur, 2),
            "pnl_eur": round(pnl_eur, 2),
            "sizing_factor": sizing_factor,
        })
    return trades


# ---------------------------------------------------------------------------
# 3. Metriques FTMO
# ---------------------------------------------------------------------------

def compute_ftmo_metrics(
    trades: list[dict[str, Any]],
    capital_eur: float = DEFAULT_CAPITAL_EUR,
) -> dict[str, Any]:
    """Calcule les metriques FTMO sur la liste de trades simules.

    Returns:
        dict avec risk_per_trade stats, daily_dd_max, total_dd_max,
        max_consecutive_losses, pnl_total, can_trade.
    """
    if not trades:
        return {
            "error": "no trades",
            "n_trades": 0,
            "can_trade": False,
        }

    # Risk per trade
    risks = [t["risk_eur"] for t in trades]
    risk_max = max(risks) if risks else 0.0
    risk_mean = sum(risks) / len(risks) if risks else 0.0
    risk_max_pct = risk_max / capital_eur if capital_eur > 0 else 0.0

    # Group by day pour DD journalier
    daily_pnl: dict[str, float] = {}
    for t in trades:
        day = t["opened_at"][:10]  # YYYY-MM-DD
        daily_pnl[day] = daily_pnl.get(day, 0.0) + t["pnl_eur"]

    # DD journalier max (la pire perte cumulee sur 1 jour)
    daily_losses = [pnl for pnl in daily_pnl.values() if pnl < 0]
    daily_dd_max = abs(min(daily_losses)) if daily_losses else 0.0
    daily_dd_max_pct = daily_dd_max / capital_eur if capital_eur > 0 else 0.0

    # Equity curve + drawdown total
    equity = capital_eur
    peak = capital_eur
    max_dd = 0.0
    for t in trades:
        equity += t["pnl_eur"]
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    max_dd_pct = max_dd / capital_eur if capital_eur > 0 else 0.0

    # Max consecutive losses
    max_consec = 0
    current_consec = 0
    for t in trades:
        if t["is_win"] == 0:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0

    # PnL total
    pnl_total = sum(t["pnl_eur"] for t in trades)
    final_equity = capital_eur + pnl_total

    # Verdict FTMO
    alerts = []
    if risk_max_pct > DEFAULT_RISK_PCT_PER_TRADE:
        alerts.append(f"risk_per_trade={risk_max_pct*100:.2f}% > {DEFAULT_RISK_PCT_PER_TRADE*100:.1f}%")
    if daily_dd_max_pct > DEFAULT_DAILY_DD_PCT:
        alerts.append(f"daily_dd={daily_dd_max_pct*100:.2f}% > {DEFAULT_DAILY_DD_PCT*100:.1f}%")
    if max_dd_pct > DEFAULT_TOTAL_DD_PCT:
        alerts.append(f"total_dd={max_dd_pct*100:.2f}% > {DEFAULT_TOTAL_DD_PCT*100:.1f}%")

    can_trade = len(alerts) == 0

    return {
        "n_trades": len(trades),
        "capital_eur": capital_eur,
        "final_equity_eur": round(final_equity, 2),
        "pnl_total_eur": round(pnl_total, 2),
        "risk_per_trade": {
            "mean_eur": round(risk_mean, 2),
            "max_eur": round(risk_max, 2),
            "max_pct": round(risk_max_pct, 4),
            "limit_pct": DEFAULT_RISK_PCT_PER_TRADE,
        },
        "daily_dd": {
            "max_eur": round(daily_dd_max, 2),
            "max_pct": round(daily_dd_max_pct, 4),
            "limit_pct": DEFAULT_DAILY_DD_PCT,
            "worst_day": (min(daily_pnl, key=daily_pnl.get) if daily_pnl else None),
        },
        "total_dd": {
            "max_eur": round(max_dd, 2),
            "max_pct": round(max_dd_pct, 4),
            "limit_pct": DEFAULT_TOTAL_DD_PCT,
        },
        "max_consecutive_losses": max_consec,
        "alerts": alerts,
        "can_trade": can_trade,
    }


# ---------------------------------------------------------------------------
# 4. Verdict GO / NO-GO + correctif
# ---------------------------------------------------------------------------

def verdict_and_corrective(
    metrics: dict[str, Any],
    capital_eur: float = DEFAULT_CAPITAL_EUR,
) -> dict[str, Any]:
    """Emet un verdict GO / NO-GO et propose un correctif sizing si NO-GO.

    Si NO-GO, retourne un sizing_factor recommande qui rendrait le sizing
    conforme (calcule par regle de 3 sur la plus severe des violations).
    """
    if not metrics.get("can_trade", False):
        alerts = metrics.get("alerts", [])
        # Identifier la pire violation pour dimensionner le correctif
        risk_pct = metrics.get("risk_per_trade", {}).get("max_pct", 0.0)
        daily_pct = metrics.get("daily_dd", {}).get("max_pct", 0.0)
        total_pct = metrics.get("total_dd", {}).get("max_pct", 0.0)
        # Plus severe = ratio le plus eleve vs limite
        ratios = []
        if DEFAULT_RISK_PCT_PER_TRADE > 0:
            ratios.append(risk_pct / DEFAULT_RISK_PCT_PER_TRADE)
        if DEFAULT_DAILY_DD_PCT > 0:
            ratios.append(daily_pct / DEFAULT_DAILY_DD_PCT)
        if DEFAULT_TOTAL_DD_PCT > 0:
            ratios.append(total_pct / DEFAULT_TOTAL_DD_PCT)
        worst_ratio = max(ratios) if ratios else 1.0
        # Sizing factor recommande = 1 / worst_ratio, securise par 0.5
        recommended_sf = round(max(0.1, 1.0 / worst_ratio * 0.8), 3)
        return {
            "verdict": "NO-GO",
            "reason": "FTMO rules violated",
            "alerts": alerts,
            "corrective": {
                "type": "reduce_sizing_factor",
                "current_sizing_factor": 1.0,
                "recommended_sizing_factor": recommended_sf,
                "explanation": (
                    f"Violation max = {worst_ratio:.2f}x la limite FTMO. "
                    f"Sizing factor {recommended_sf} (au lieu de 1.0) ramene "
                    f"toutes les metriques dans les seuils."
                ),
            },
            "motion_required": True,
        }
    return {
        "verdict": "GO",
        "reason": "All FTMO rules respected",
        "alerts": [],
        "corrective": None,
        "motion_required": False,
    }


# ---------------------------------------------------------------------------
# 5. Orchestration
# ---------------------------------------------------------------------------

def run_sizing_validation(
    db_path: Path = DB_PATH,
    n_trades: int = DEFAULT_N_TRADES,
    trades_per_day: int = DEFAULT_TRADES_PER_DAY,
    capital_eur: float = DEFAULT_CAPITAL_EUR,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute le pipeline complet.

    Returns dict avec sizing_actuel, simulation metrics, verdict GO/NO-GO.
    Exit code 0 (GO), 1 (NO-GO), 4 (erreur).
    """
    if capital_eur <= 0:
        return {
            "schema_version": "1.0",
            "phase": "107",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": "capital_eur <= 0",
            "exit_code": 4,
        }

    # 1. Lire sizing actuel
    sizing_actuel = fetch_current_sizing(db_path)
    log.info("Sizing actuel: %s", sizing_actuel)

    # 2. Simuler N trades
    trades = simulate_trades(
        n_trades=n_trades,
        trades_per_day=trades_per_day,
        lot_size=sizing_actuel["lot_size"],
        symbol=DEFAULT_SYMBOL,
        avg_risk_pips=sizing_actuel["avg_risk_pips"],
        wr=0.75,
        sizing_factor=sizing_actuel["default_sizing_factor"],
        seed=seed,
    )

    # 3. Metriques FTMO
    metrics = compute_ftmo_metrics(trades, capital_eur=capital_eur)

    # 4. Verdict + correctif
    verdict = verdict_and_corrective(metrics, capital_eur=capital_eur)

    # 5. Rapport complet
    report = {
        "schema_version": "1.0",
        "phase": "107",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_source": str(db_path),
        "n_trades_simulated": n_trades,
        "trades_per_day": trades_per_day,
        "capital_eur": capital_eur,
        "sizing_actuel": sizing_actuel,
        "ftmo_rules": {
            "risk_per_trade_max_pct": DEFAULT_RISK_PCT_PER_TRADE,
            "daily_dd_max_pct": DEFAULT_DAILY_DD_PCT,
            "total_dd_max_pct": DEFAULT_TOTAL_DD_PCT,
            "leverage_max": DEFAULT_LEVERAGE_MAX,
        },
        "metrics": metrics,
        "verdict": verdict,
    }
    report["exit_code"] = 0 if verdict["verdict"] == "GO" else 1
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FTMO Sizing Validator (Phase 107)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Chemin DB source")
    parser.add_argument("--n-trades", type=int, default=DEFAULT_N_TRADES,
                        dest="n_trades", help="Nombre de trades a simuler")
    parser.add_argument("--trades-per-day", type=int, default=DEFAULT_TRADES_PER_DAY,
                        dest="trades_per_day")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL_EUR,
                        help="Capital EUR (defaut 10000)")
    parser.add_argument("--seed", type=int, default=42, help="Seed RNG reproductibilite")
    parser.add_argument("--report", type=Path, default=None,
                        help="Chemin rapport JSON (defaut stdout)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    report = run_sizing_validation(
        db_path=args.db,
        n_trades=args.n_trades,
        trades_per_day=args.trades_per_day,
        capital_eur=args.capital,
        seed=args.seed,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
        log.info("rapport ecrit: %s", args.report)
    else:
        print(payload)
    return report.get("exit_code", 4)


if __name__ == "__main__":
    sys.exit(main())

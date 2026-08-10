"""CEO-OPT4 : Dashboard CEO temps réel — métriques décisionnelles.

Rapport JSON : reports/ceo_dashboard_{ts}.json
Affichage console lisible en 10 secondes.
R6 fail-open par section | R9 JSON | R10 lecture seule.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ceo_kelly_optimizer import compute_adaptive_kelly
from ceo_circuit_breaker import check_circuit_breaker
from ceo_quant_edge_scorer import compute_edge_score

DB_PATH    = Path("data/v10_decisions.db")
REPORT_DIR = Path("reports")


def _load_recent_trades(db_path: Path, limit: int = 50) -> list[dict]:
    """Charge les derniers trades shadow."""
    try:
        if not db_path.exists():
            return []
        with sqlite3.connect(db_path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT result, pnl_pips, resolved_at, pair, timeframe
                FROM shadow_trades
                WHERE result IN ('WIN','LOSS','SL')
                ORDER BY resolved_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _compute_wr_pf(trades: list[dict]) -> dict:
    """WR + PF depuis liste trades."""
    if not trades:
        return {"wr": None, "pf": None, "n": 0}
    wins   = [t for t in trades if t.get("result") == "WIN"]
    losses = [t for t in trades if t.get("result") in ("LOSS", "SL")]
    wr     = len(wins) / len(trades)
    gross_win  = sum(t.get("pnl_pips", 0) for t in wins)
    gross_loss = abs(sum(t.get("pnl_pips", 0) for t in losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else None
    return {"wr": round(wr, 4), "pf": round(pf, 3) if pf else None, "n": len(trades)}


def run_ceo_dashboard(
    db_path: Path = DB_PATH,
    force_delta: float = 0.0,
    pre_wave_phase: str = "NEUTRAL",
    regime: str = "UNKNOWN",
    signal_level: str = "A2",
    atr_current: Optional[float] = None,
) -> dict:
    """Génère le dashboard CEO complet."""
    now_ts = datetime.now(timezone.utc)
    ts = now_ts.strftime("%Y%m%d_%H%M%S")

    # 1. Trades récents
    trades = _load_recent_trades(db_path)
    stats_50  = _compute_wr_pf(trades[:50])
    stats_20  = _compute_wr_pf(trades[:20])

    # 2. Circuit-breaker
    circuit = check_circuit_breaker(db_path, now_ts)

    # 3. Kelly
    kelly = compute_adaptive_kelly(
        recent_trades=trades[:20],
        atr_current=atr_current,
        rr_target=1.5,
        window=20,
    )

    # 4. Edge score
    force_history = [t.get("pnl_pips", 0) for t in trades[:30]]
    edge = compute_edge_score(
        force_delta=force_delta,
        force_history=force_history if len(force_history) >= 5 else None,
        pre_wave_phase=pre_wave_phase,
        regime=regime,
        signal_level=signal_level,
    )

    # 5. GO / NO-GO décision CEO
    go_live = (
        not circuit.is_open
        and edge.go
        and kelly.fraction >= 0.005
        and (stats_20["wr"] or 0) >= 0.48
    )

    report = {
        "timestamp": now_ts.isoformat(),
        "version": "C22-CEO",
        "go_live_decision": go_live,
        "circuit_breaker": circuit.as_dict(),
        "kelly": kelly.as_dict(),
        "edge_score": edge.as_dict(),
        "performance": {
            "last_20_trades": stats_20,
            "last_50_trades": stats_50,
        },
        "context": {
            "force_delta": force_delta,
            "pre_wave_phase": pre_wave_phase,
            "regime": regime,
            "signal_level": signal_level,
            "atr_current": atr_current,
        },
    }

    # Rapport JSON
    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / f"ceo_dashboard_{ts}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Affichage console CEO
    _print_dashboard(report)
    return report


def _print_dashboard(r: dict) -> None:
    go   = r["go_live_decision"]
    cb   = r["circuit_breaker"]
    kel  = r["kelly"]
    edge = r["edge_score"]
    p20  = r["performance"]["last_20_trades"]
    status = "🟢 GO" if go else "🔴 NO-GO"
    print(f"\n{'='*60}")
    print(f"  PowerFlow V10 — CEO DASHBOARD {r['timestamp'][:19]}")
    print(f"{'='*60}")
    print(f"  DÉCISION          : {status}")
    print(f"  Circuit-Breaker   : {cb['level']} | streak={cb['streak_count']} | open={cb['is_open']}")
    print(f"  Kelly Fraction    : {kel['fraction']:.4f} ({kel['method']})")
    print(f"  Edge Score        : {edge['score']:.3f} [{edge['grade']}] | Z-force={edge['z_force']:.2f}")
    print(f"  WR last 20        : {p20['wr'] or 'N/A'} | PF={p20['pf'] or 'N/A'} | n={p20['n']}")
    print(f"  Phase             : {r['context']['pre_wave_phase']} | Regime={r['context']['regime']}")
    print(f"  Reason CB         : {cb['reason']}")
    print(f"  Reason Kelly      : {kel['rationale'][:60]}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CEO Dashboard V10")
    parser.add_argument("--force-delta",    type=float, default=0.0)
    parser.add_argument("--phase",          default="NEUTRAL")
    parser.add_argument("--regime",         default="UNKNOWN")
    parser.add_argument("--signal-level",   default="A2")
    parser.add_argument("--atr",            type=float, default=None)
    args = parser.parse_args()
    run_ceo_dashboard(
        force_delta=args.force_delta,
        pre_wave_phase=args.phase,
        regime=args.regime,
        signal_level=args.signal_level,
        atr_current=args.atr,
    )

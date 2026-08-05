"""V10 Risk Dashboard — exerce le bouclier R10 sur les positions live (Sprint 11).

Charge les dernières positions paper live, applique le risk shield (DD halt,
position max, net exposure, corrélation) et produit un rapport R10.

R9 honnête : DD/positions depuis proxy paper (is_win_proxy). R10 : compute only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_risk_shield import evaluate_risk_shield  # noqa: E402
from core.v10.v10_net_exposure import (  # noqa: E402
    Position as NetPosition, compute_net_exposure,
)

log = logging.getLogger(__name__)
DEFAULT_DB = ROOT / "data" / "v9_forces.db"


def load_open_positions(db_path: Path, limit: int = 20) -> list:
    """Charge les N dernières positions paper comme positions OPEN simulées."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT trade_id, symbol, direction, pips_simulated "
            "FROM paper_trades ORDER BY closed_at DESC LIMIT ?", (limit,)
        ).fetchall()
    except Exception:
        rows = conn.execute(
            "SELECT trade_id, symbol, direction, pips_simulated "
            "FROM paper_trades LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    positions = []
    for tid, sym, direction, pips in rows:
        pos_dir = "long" if "haussiere" in str(direction).lower() or \
            str(direction).lower() in ("long", "buy", "1") else "short"
        positions.append(NetPosition(
            position_id=str(tid), pair=str(sym), direction=pos_dir,
            lot_size=0.01, status="OPEN",
        ))
    return positions


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    positions = load_open_positions(db)
    net = compute_net_exposure(positions)
    log.info("Chargé %d positions, net exposure: %s", len(positions), net.exposures)

    # Exerce le risk shield sur chaque position comme candidate
    shield_results = []
    for p in positions:
        dec = evaluate_risk_shield(
            p.pair, p.direction,
            daily_dd_pct=0.0, candidate_risk_pct=0.5,
            exposure_gate_result=None, portfolio_can_enter=True,
        )
        shield_results.append({
            "pair": p.pair, "direction": p.direction,
            "can_enter": dec.can_enter,
            "blocked_reasons": dec.blocked_reasons,
            "gates": dict(dec.gates),
        })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_positions": len(positions),
        "net_exposure": {k: round(v, 4) for k, v in net.exposures.items()},
        "shield_results": shield_results,
        "audit": {
            "r9_honest": "positions simulées depuis paper_trades proxy — DD 0.0",
            "r10": "compute only, zero order real",
        },
    }

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_risk_dashboard_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Rapport risk dashboard écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())

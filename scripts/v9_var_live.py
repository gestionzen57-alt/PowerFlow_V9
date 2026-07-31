"""v9_var_live.py — Phase 25A motion CEO autopilote.

Value at Risk live sur les paper trades fermes.
Calcule VaR 95% et VaR 99% (perte max probable sur 1 trade).

CVaR (Expected Shortfall) : moyenne des pertes au-dessus du VaR.

Auteur : Hermes (Phase 25A motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.var")


def get_paper_trades_pips(db_path: Path | str) -> list[float]:
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("""
                SELECT pips_net FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
            """).fetchall()
            return [float(r[0] or 0) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def compute_var(pips_list: list[float], confidence: float = 0.95) -> dict:
    """Calcule VaR et CVaR au seuil de confiance donne.

    VaR = quantile inferieur (ex 5% pour 95% confiance)
    CVaR = moyenne des pertes sous le VaR
    """
    if not pips_list or len(pips_list) < 10:
        return {"error": "insufficient_data"}
    losses = sorted([p for p in pips_list if p < 0])
    if not losses:
        return {"error": "no_losses"}
    # VaR : quantile au niveau (1 - confidence)
    idx = int(len(losses) * (1 - confidence))
    idx = min(idx, len(losses) - 1)
    var = losses[idx]
    # CVaR : moyenne des pertes au-dessus du VaR (pire que VaR)
    cvar_losses = losses[:idx + 1] if idx > 0 else losses[:1]
    cvar = sum(cvar_losses) / len(cvar_losses)
    return {
        "confidence": confidence,
        "n_trades": len(pips_list),
        "n_losses": len(losses),
        "var_pips": round(var, 2),
        "cvar_pips": round(cvar, 2),
        "worst_loss": round(min(losses), 2),
        "best_loss": round(max(losses), 2),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 VaR live (Phase 25A)",
    )
    parser.add_argument("--confidence", type=float, default=0.95)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    pips = get_paper_trades_pips(DB_PATH)
    result = compute_var(pips, confidence=args.confidence)

    print("=" * 70)
    print("PHASE 25A — VALUE AT RISK")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1
    print(f"Confiance          : {result['confidence'] * 100:.0f}%")
    print(f"N trades           : {result['n_trades']}")
    print(f"N losses           : {result['n_losses']}")
    print()
    print(f"VaR ({result['confidence'] * 100:.0f}%)       : {result['var_pips']:+.2f} pips")
    print(f"CVaR (Expected Shortfall) : {result['cvar_pips']:+.2f} pips")
    print(f"Worst loss         : {result['worst_loss']:+.2f} pips")
    print()
    if result["var_pips"] >= -10:
        print(">>> VaR raisonnable (<= 10 pips perte max)")
    elif result["var_pips"] >= -25:
        print(">>> VaR eleve (> 10 pips perte max)")
    else:
        print(">>> VaR TRES ELEVE (> 25 pips perte max)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())
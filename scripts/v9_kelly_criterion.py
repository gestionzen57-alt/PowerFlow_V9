"""v9_kelly_criterion.py — Phase 23 motion CEO « EDGE FUND MAX ».

Kelly criterion sizing optimal pour maximiser la croissance long-terme.
Calcule le pourcentage du capital a risquer par trade base sur WR + RR.

Kelly % = (W * (R+1) - 1) / R
  ou W = win rate, R = reward/risk ratio (TP/SL)

Note : utilise 1/4 Kelly (fractional) pour plus de securite.

Auteur : Hermes (Phase 23 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.kelly_criterion")


def compute_kelly(win_rate: float, reward_risk: float,
                  fractional: float = 0.25) -> dict:
    """Calcule Kelly criterion.

    Args:
        win_rate: WR entre 0 et 1 (ex 0.946 pour 94.6%)
        reward_risk: ratio gain/perte (ex 25/8 = 3.125)
        fractional: fraction de Kelly (defaut 0.25 = quarter Kelly)
    """
    if not 0 <= win_rate <= 1:
        return {"error": "win_rate_out_of_range"}
    if reward_risk <= 0:
        return {"error": "reward_risk_must_be_positive"}
    if not 0 < fractional <= 1:
        return {"error": "fractional_out_of_range"}

    kelly_full = (win_rate * (reward_risk + 1) - 1) / reward_risk
    kelly_fractional = kelly_full * fractional
    # Cap a 25% (jamais plus d'1/4 capital sur un trade)
    kelly_safe = min(kelly_fractional, 0.25)
    # Pas de trade si Kelly <= 0
    if kelly_full <= 0:
        return {
            "win_rate": win_rate,
            "reward_risk": reward_risk,
            "kelly_full": round(kelly_full, 4),
            "kelly_fractional": round(kelly_fractional, 4),
            "kelly_safe": 0.0,
            "recommendation": "NO_TRADE_NEGATIVE_KELLY",
        }
    return {
        "win_rate": win_rate,
        "reward_risk": reward_risk,
        "kelly_full": round(kelly_full, 4),
        "kelly_fractional": round(kelly_fractional, 4),
        "kelly_safe": round(kelly_safe, 4),
        "fractional": fractional,
        "recommendation": (
            "AGGRESSIVE" if kelly_full > 0.5
            else "MODERATE" if kelly_full > 0.2
            else "CONSERVATIVE" if kelly_full > 0.05
            else "MICRO"
        ),
    }


def compute_lot_size(kelly_safe: float, capital: float,
                     stop_loss_pips: float, pip_value: float = 10.0) -> dict:
    """Calcule le lot size depuis Kelly safe + capital + SL.

    pip_value = valeur d'1 pip pour 1 lot standard (typiquement 10 USD
    pour GBPUSD sur compte USD).
    """
    risk_amount = capital * kelly_safe
    # lot = risk_amount / (SL_pips * pip_value_per_lot)
    pip_value_per_lot = pip_value
    lot = risk_amount / (stop_loss_pips * pip_value_per_lot)
    return {
        "capital": capital,
        "kelly_safe": kelly_safe,
        "risk_amount": round(risk_amount, 2),
        "stop_loss_pips": stop_loss_pips,
        "lot_size": round(lot, 4),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 Kelly criterion (Phase 23 quantique)",
    )
    parser.add_argument("--wr", type=float, default=0.946,
                        help="Win rate (defaut 0.946 = 94.6%%)")
    parser.add_argument("--tp", type=float, default=25.0,
                        help="Take profit pips (defaut 25)")
    parser.add_argument("--sl", type=float, default=8.0,
                        help="Stop loss pips (defaut 8)")
    parser.add_argument("--fractional", type=float, default=0.25,
                        help="Fraction de Kelly (defaut 0.25)")
    parser.add_argument("--capital", type=float, default=10000.0,
                        help="Capital (defaut 10000)")
    args = parser.parse_args(argv)

    rr = args.tp / args.sl
    kelly = compute_kelly(args.wr, rr, fractional=args.fractional)

    print("=" * 70)
    print("PHASE 23 — KELLY CRITERION")
    print("=" * 70)
    print(f"Win rate        : {args.wr * 100:.1f}%")
    print(f"TP / SL         : {args.tp}p / {args.sl}p")
    print(f"Reward/Risk     : {rr:.3f}")
    print(f"Fractional      : {args.fractional} (={int(args.fractional * 100)}% Kelly)")
    print()
    if "error" in kelly:
        print(f"Erreur : {kelly['error']}")
        return 1
    print(f"Kelly full      : {kelly['kelly_full'] * 100:.2f}%")
    print(f"Kelly fractional: {kelly['kelly_fractional'] * 100:.2f}%")
    print(f"Kelly safe cap  : {kelly['kelly_safe'] * 100:.2f}% (cap 25%)")
    print(f"Recommendation  : {kelly['recommendation']}")
    print()

    lot_info = compute_lot_size(kelly["kelly_safe"], args.capital, args.sl)
    print(f"Capital         : {args.capital:.0f}")
    print(f"Risk per trade  : {lot_info['risk_amount']:.2f}")
    print(f"SL pips         : {lot_info['stop_loss_pips']}")
    print(f"Lot size optimal: {lot_info['lot_size']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())